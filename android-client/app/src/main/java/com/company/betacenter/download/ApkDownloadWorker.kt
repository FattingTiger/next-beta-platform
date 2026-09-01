package com.company.betacenter.download

import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.Data
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import androidx.work.await
import androidx.work.workDataOf
import com.company.betacenter.BetaCenterApplication
import com.company.betacenter.data.ApiException
import com.company.betacenter.data.AppDetails
import com.company.betacenter.data.DownloadTicket
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.withTimeoutOrNull
import kotlinx.coroutines.withContext
import java.io.File
import java.io.IOException
import java.security.MessageDigest
import java.util.UUID
import java.util.concurrent.TimeUnit

class DownloadScheduler(private val context: Context) {
    private val workManager = WorkManager.getInstance(context)

    fun enqueue(app: AppDetails, userId: String): UUID {
        require(userId.isNotBlank()) { "userId must not be blank" }
        val version = requireNotNull(app.currentVersion)
        val requestId = UUID.randomUUID().toString()
        val work = OneTimeWorkRequestBuilder<ApkDownloadWorker>()
            .setInputData(
                workDataOf(
                    KEY_APP_ID to app.id,
                    KEY_USER_ID to userId,
                    KEY_VERSION_ID to version.id,
                    KEY_PACKAGE_NAME to app.packageName,
                    KEY_VERSION_NAME to version.versionName,
                    KEY_VERSION_CODE to version.versionCode,
                    KEY_FILE_SIZE to version.fileSize,
                    KEY_SHA256 to version.sha256,
                    KEY_SIGNING_CERT to version.signingCertSha256,
                    KEY_CLIENT_REQUEST_ID to requestId,
                ),
            )
            .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 10, TimeUnit.SECONDS)
            .addTag(downloadTag(userId, version.id))
            .addTag(userTag(userId))
            .addTag(ALL_DOWNLOADS_TAG)
            .build()
        workManager.enqueueUniqueWork(uniqueName(userId, version.id), ExistingWorkPolicy.KEEP, work)
        return work.id
    }

    fun cancel(userId: String, versionId: String) = workManager.cancelUniqueWork(uniqueName(userId, versionId))

    /**
     * Cancels and removes downloads owned by one account only. WorkManager
     * cancellation is issued immediately, while the bounded wait gives a
     * running worker a chance to report cancellation with the still-current
     * session before its files are removed.
     */
    suspend fun clearForUser(userId: String) {
        require(userId.isNotBlank()) { "userId must not be blank" }

        // Issue the current-format owner cancellation before doing any legacy
        // discovery so active downloads are interrupted without query delay.
        val ownerCancellation = workManager.cancelAllWorkByTag(userTag(userId))
        try {
        val legacyWork = withContext(Dispatchers.IO) {
            runCatching {
                workManager.getWorkInfosByTag(ALL_DOWNLOADS_TAG)
                    .get(LEGACY_QUERY_TIMEOUT_MILLIS, TimeUnit.MILLISECONDS)
            }.getOrDefault(emptyList())
        }.filter { info ->
                info.tags.any { tag -> tag.startsWith(legacyDownloadTagPrefix(userId)) }
            }
            val legacyCancellations = legacyWork.map { info -> workManager.cancelWorkById(info.id) }
            withTimeoutOrNull(CANCELLATION_GRACE_MILLIS) {
                ownerCancellation.await()
                legacyCancellations.forEach { operation -> operation.await() }
            }
        } finally {
            withContext(NonCancellable + Dispatchers.IO) {
                deleteDownloadsForUser(context.filesDir, userId)
            }
        }
    }

    fun isOwnedFile(userId: String, path: String?): Boolean =
        isOwnedDownloadFile(context.filesDir, userId, path)

    fun workManager(): WorkManager = workManager

    companion object {
        const val ALL_DOWNLOADS_TAG = "beta-center-download"
        private const val LEGACY_QUERY_TIMEOUT_MILLIS = 750L
        private const val CANCELLATION_GRACE_MILLIS = 2_500L

        fun userTag(userId: String) = "$ALL_DOWNLOADS_TAG:user:${downloadOwnerKey(userId)}"
        fun downloadTag(userId: String, versionId: String) =
            "${userTag(userId)}:version:${downloadOwnerKey(versionId)}"
        fun uniqueName(userId: String, versionId: String) =
            "$ALL_DOWNLOADS_TAG-${downloadOwnerKey(userId)}-${downloadOwnerKey(versionId)}"

        internal fun legacyDownloadTagPrefix(userId: String) = "$ALL_DOWNLOADS_TAG:$userId:"
    }
}

class ApkDownloadWorker(
    appContext: Context,
    params: WorkerParameters,
) : CoroutineWorker(appContext, params) {
    private val api = (appContext.applicationContext as BetaCenterApplication).container.api

    override suspend fun doWork(): Result {
        val userId = inputData.getString(KEY_USER_ID)?.takeIf(String::isNotBlank) ?: return invalidInput()
        val versionId = inputData.getString(KEY_VERSION_ID) ?: return invalidInput()
        val packageName = inputData.getString(KEY_PACKAGE_NAME) ?: return invalidInput()
        val versionName = inputData.getString(KEY_VERSION_NAME) ?: return invalidInput()
        val versionCode = inputData.getLong(KEY_VERSION_CODE, -1L)
        val expectedFileSize = inputData.getLong(KEY_FILE_SIZE, -1L)
        val expectedSha256 = inputData.getString(KEY_SHA256) ?: return invalidInput()
        val signingCert = inputData.getString(KEY_SIGNING_CERT) ?: return invalidInput()
        val clientRequestId = inputData.getString(KEY_CLIENT_REQUEST_ID) ?: return invalidInput()
        if (versionCode < 0L || expectedFileSize <= 0L || expectedSha256.length != 64) return invalidInput()

        val directory = userDownloadDirectory(applicationContext.filesDir, userId)
        directory.mkdirs()
        val finalFile = File(directory, "$clientRequestId.apk")
        val partFile = File(directory, "$clientRequestId.apk.part")
        var ticket: DownloadTicket? = null
        try {
            ensureSameUser(userId)
            setProgress(workDataOf(KEY_PHASE to PHASE_PREPARING, KEY_PROGRESS to 0))
            ticket = try {
                api.startDownload(versionId, clientRequestId)
            } catch (exception: ApiException) {
                if (
                    exception.errorCode == "download_already_completed" &&
                    validateFile(
                        finalFile,
                        expectedFileSize,
                        expectedSha256,
                        packageName,
                        versionName,
                        versionCode,
                        signingCert,
                    )
                ) {
                    return readyResult(finalFile, packageName, versionName)
                }
                throw exception
            }
            if (
                ticket.fileSize != expectedFileSize ||
                !ticket.sha256.equals(expectedSha256, ignoreCase = true)
            ) {
                throw ApiException(502, "download_metadata_mismatch", "服务端下载信息与应用版本不一致")
            }

            if (
                !validateFile(
                    finalFile,
                    expectedFileSize,
                    expectedSha256,
                    packageName,
                    versionName,
                    versionCode,
                    signingCert,
                )
            ) {
                finalFile.delete()
                var lastProgress = -1
                api.downloadFile(ticket, partFile) { bytes, total ->
                    val percent = if (total <= 0L) 0 else ((bytes * 100L) / total).toInt().coerceIn(0, 100)
                    if (percent != lastProgress) {
                        lastProgress = percent
                        setProgressAsync(
                            workDataOf(
                                KEY_PHASE to PHASE_DOWNLOADING,
                                KEY_PROGRESS to percent,
                                KEY_BYTES to bytes,
                                KEY_TOTAL to total,
                            ),
                        )
                    }
                }
                setProgress(workDataOf(KEY_PHASE to PHASE_VERIFYING, KEY_PROGRESS to 100))
                if (
                    !validateFile(
                        partFile,
                        expectedFileSize,
                        expectedSha256,
                        packageName,
                        versionName,
                        versionCode,
                        signingCert,
                    )
                ) {
                    partFile.delete()
                    api.failDownload(ticket.downloadId, "APK 完整性或签名校验失败")
                    return Result.failure(errorData("APK 校验未通过，已删除下载文件"))
                }
                if (!partFile.renameTo(finalFile)) {
                    partFile.copyTo(finalFile, overwrite = true)
                    partFile.delete()
                }
            }
            ensureSameUser(userId)

            api.completeDownload(ticket.downloadId, ticket.sha256, finalFile.length())
            return readyResult(finalFile, packageName, versionName)
        } catch (cancelled: CancellationException) {
            withContext(NonCancellable) {
                if (api.currentDownloadSession()?.user?.id == userId) {
                    ticket?.let { runCatching { api.failDownload(it.downloadId, "用户取消下载", cancelled = true) } }
                }
                partFile.delete()
                finalFile.delete()
            }
            throw cancelled
        } catch (exception: Exception) {
            val retry = isRecoverable(exception) && runAttemptCount < MAX_ATTEMPTS
            if (retry) return Result.retry()
            if (api.currentDownloadSession()?.user?.id == userId) {
                ticket?.let { runCatching { api.failDownload(it.downloadId, safeReason(exception)) } }
            }
            partFile.delete()
            finalFile.delete()
            return Result.failure(errorData(safeReason(exception)))
        }
    }

    private fun validateFile(
        file: File,
        expectedFileSize: Long,
        expectedSha256: String,
        expectedPackage: String,
        expectedVersionName: String,
        expectedVersionCode: Long,
        expectedSigningCert: String,
    ): Boolean {
        if (!file.isFile || file.length() != expectedFileSize) return false
        if (!sha256(file).equals(expectedSha256, ignoreCase = true)) return false
        val packageManager = applicationContext.packageManager
        val flags = if (Build.VERSION.SDK_INT >= 28) {
            PackageManager.GET_SIGNING_CERTIFICATES
        } else {
            @Suppress("DEPRECATION")
            PackageManager.GET_SIGNATURES
        }
        val info = packageManager.getPackageArchiveInfo(file.absolutePath, flags) ?: return false
        val archiveVersionCode = if (Build.VERSION.SDK_INT >= 28) {
            info.longVersionCode
        } else {
            @Suppress("DEPRECATION")
            info.versionCode.toLong()
        }
        if (info.packageName != expectedPackage) return false
        if (archiveVersionCode != expectedVersionCode) return false
        if (info.versionName.orEmpty() != expectedVersionName) return false
        val certificateHashes = if (Build.VERSION.SDK_INT >= 28) {
            info.signingInfo?.apkContentsSigners.orEmpty().map { signature -> sha256(signature.toByteArray()) }
        } else {
            @Suppress("DEPRECATION")
            info.signatures.orEmpty().map { signature -> sha256(signature.toByteArray()) }
        }
        return normalizeHash(expectedSigningCert) in certificateHashes.map(::normalizeHash)
    }

    private fun readyResult(file: File, packageName: String, versionName: String): Result =
        Result.success(
            workDataOf(
                KEY_PHASE to PHASE_READY,
                KEY_PROGRESS to 100,
                KEY_FILE_PATH to file.absolutePath,
                KEY_PACKAGE_NAME to packageName,
                KEY_VERSION_NAME to versionName,
            ),
        )

    private fun ensureSameUser(expectedUserId: String) {
        if (api.currentDownloadSession()?.user?.id != expectedUserId) {
            throw ApiException(401, "download_user_changed", "登录账户已变化，请重新开始下载")
        }
    }

    private fun sha256(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().buffered(64 * 1024).use { input ->
            val buffer = ByteArray(64 * 1024)
            while (true) {
                val count = input.read(buffer)
                if (count < 0) break
                digest.update(buffer, 0, count)
            }
        }
        return digest.digest().toHex()
    }

    private fun sha256(bytes: ByteArray): String =
        MessageDigest.getInstance("SHA-256").digest(bytes).toHex()

    private fun ByteArray.toHex(): String = joinToString("") { byte -> "%02x".format(byte) }
    private fun normalizeHash(value: String): String = value.lowercase().replace(":", "")

    private fun isRecoverable(exception: Exception): Boolean = when (exception) {
        is IOException -> true
        is ApiException -> exception.statusCode == 408 || exception.statusCode == 429 || exception.statusCode >= 500 ||
            exception.errorCode == "download_unavailable"
        else -> false
    }

    private fun safeReason(exception: Exception): String = when (exception) {
        is ApiException -> exception.message
        is IOException -> "网络连接中断，请稍后重试"
        else -> exception.message?.takeIf(String::isNotBlank) ?: "下载未完成"
    }.take(300)

    private fun invalidInput(): Result = Result.failure(errorData("下载任务参数不完整"))
    private fun errorData(message: String): Data = workDataOf(KEY_ERROR to message.take(300))

    private companion object {
        const val MAX_ATTEMPTS = 3
    }
}

const val KEY_APP_ID = "app_id"
const val KEY_USER_ID = "user_id"
const val KEY_VERSION_ID = "version_id"
const val KEY_PACKAGE_NAME = "package_name"
const val KEY_VERSION_NAME = "version_name"
const val KEY_VERSION_CODE = "version_code"
const val KEY_FILE_SIZE = "file_size"
const val KEY_SHA256 = "sha256"
const val KEY_SIGNING_CERT = "signing_cert"
const val KEY_CLIENT_REQUEST_ID = "client_request_id"
const val KEY_PHASE = "phase"
const val KEY_PROGRESS = "progress"
const val KEY_BYTES = "bytes"
const val KEY_TOTAL = "total"
const val KEY_FILE_PATH = "file_path"
const val KEY_ERROR = "error"

const val PHASE_PREPARING = "preparing"
const val PHASE_DOWNLOADING = "downloading"
const val PHASE_VERIFYING = "verifying"
const val PHASE_READY = "ready"
