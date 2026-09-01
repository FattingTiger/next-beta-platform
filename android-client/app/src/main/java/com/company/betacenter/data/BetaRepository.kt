package com.company.betacenter.data

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import android.os.Build
import androidx.core.graphics.scale
import com.company.betacenter.BuildConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.withContext
import java.io.File
import java.io.FileOutputStream
import java.io.InputStream
import java.util.UUID

class BetaRepository(
    private val context: Context,
    private val api: ApiClient,
) {
    fun currentSession(): AuthSession? = api.currentSession()
    fun retiringSession(): AuthSession? = api.retiringSession()

    suspend fun login(phone: String, password: String) = api.login(phone, password)
    fun markLocalSessionRetiring(): AuthSession? = api.markLocalSessionRetiring()
    fun clearLocalSession(): String? = api.clearLocalSession()
    suspend fun revokeSession(accessToken: String?) = api.revokeSession(accessToken)
    suspend fun changePassword(current: String, replacement: String) = api.changePassword(current, replacement)
    suspend fun apps(search: String = "") = api.listApps(search)
    suspend fun app(appId: String) = api.getApp(appId)
    suspend fun bugs(mine: Boolean = false, appId: String? = null, page: Int = 1, pageSize: Int = 50) =
        api.listBugs(mine = mine, appId = appId, page = page, pageSize = pageSize)
    suspend fun bugCounts(appId: String): Map<BugState, Int> = coroutineScope {
        listOf(BugState.PENDING, BugState.IN_PROGRESS, BugState.VERIFYING, BugState.CLOSED)
            .map { status -> async { status to api.listBugs(appId = appId, status = status, pageSize = 1).total } }
            .awaitAll()
            .toMap()
    }
    suspend fun bug(bugId: String) = api.getBug(bugId)
    suspend fun updateBugText(bugId: String, update: BugTextUpdate) = api.updateBugText(bugId, update)
    suspend fun comment(bugId: String, content: String) = api.addBugComment(bugId, content)
    suspend fun verify(bugId: String, accepted: Boolean, note: String) = api.verifyBug(bugId, accepted, note)
    suspend fun privateImage(url: String) = api.loadPrivateImage(url)

    suspend fun importBugScreenshot(source: Uri): Uri = withContext(Dispatchers.IO) {
        val userId = api.currentSession()?.user?.id ?: throw ApiException(401, "not_authenticated", "请先登录")
        val prepared = prepareScreenshot(source, userId)
        val directory = draftDirectory(userId).apply { mkdirs() }
        val destination = File(directory, "evidence-${UUID.randomUUID()}.webp")
        try {
            if (!prepared.renameTo(destination)) prepared.copyTo(destination, overwrite = true)
        } catch (exception: Exception) {
            destination.delete()
            throw exception
        } finally {
            prepared.delete()
        }
        Uri.fromFile(destination)
    }

    fun deleteDraftScreenshots(uris: Collection<Uri>) {
        uris.forEach { uri ->
            val path = uri.takeIf { it.scheme == "file" }?.path ?: return@forEach
            val file = File(path).canonicalFile
            val root = File(context.filesDir, "bug-drafts").canonicalFile
            if (file.path.startsWith(root.path + File.separator)) file.delete()
        }
    }

    suspend fun submitBug(draft: BugDraft): BugReport = withContext(Dispatchers.IO) {
        val session = api.currentSession() ?: throw ApiException(401, "not_authenticated", "请先登录")
        val prepared = mutableListOf<File>()
        try {
            draft.screenshots.forEach { prepared += prepareScreenshot(it, session.user.id) }
            val fields = linkedMapOf(
                "app_id" to draft.appId,
                "version_id" to draft.versionId,
                "title" to draft.title.trim(),
                "description" to draft.description.trim(),
                "reproduction_steps" to draft.reproductionSteps.trim(),
                "device_model" to listOf(Build.MANUFACTURER, Build.MODEL).joinToString(" ").trim().take(120),
                "android_version" to Build.VERSION.RELEASE.orEmpty().take(50),
                "client_version" to BuildConfig.VERSION_NAME.take(50),
                "visibility" to draft.visibility,
            )
            val submitted = api.createBug(
                fields,
                prepared.map { image ->
                    MultipartFilePart(
                        filename = image.name,
                        contentType = "image/webp",
                        length = image.length(),
                        openStream = image::inputStream,
                    )
                },
            )
            deleteDraftScreenshots(draft.screenshots)
            submitted
        } finally {
            prepared.forEach(File::delete)
        }
    }

    private fun prepareScreenshot(source: Uri, userId: String): File {
        val stagingDirectory = File(context.cacheDir, "bug-evidence/${safeSegment(userId)}").apply { mkdirs() }
        val original = File(stagingDirectory, "${UUID.randomUUID()}.source")
        var prepared: File? = null
        var activeBitmap: Bitmap? = null
        var completed = false
        try {
            openSource(source)?.use { input ->
                FileOutputStream(original).use { output ->
                    val buffer = ByteArray(64 * 1024)
                    var total = 0L
                    while (true) {
                        val count = input.read(buffer)
                        if (count < 0) break
                        total += count
                        if (total > MAX_SOURCE_BYTES) {
                            throw IllegalArgumentException("单张截图不能超过 10 MB")
                        }
                        output.write(buffer, 0, count)
                    }
                }
            } ?: throw IllegalArgumentException("无法读取所选截图")

            val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            BitmapFactory.decodeFile(original.absolutePath, bounds)
            require(bounds.outWidth > 0 && bounds.outHeight > 0) { "所选文件不是有效图片" }
            require(bounds.outWidth <= 16_000 && bounds.outHeight <= 16_000) { "截图尺寸过大" }
            require(bounds.outWidth.toLong() * bounds.outHeight.toLong() <= 32_000_000L) { "截图像素过多" }

            var sample = 1
            while (
                bounds.outWidth / sample > TARGET_EDGE ||
                bounds.outHeight / sample > TARGET_EDGE ||
                (bounds.outWidth.toLong() / sample) * (bounds.outHeight.toLong() / sample) > MAX_DECODE_PIXELS
            ) {
                sample *= 2
            }
            val decoded = BitmapFactory.decodeFile(
                original.absolutePath,
                BitmapFactory.Options().apply { inSampleSize = sample },
            ) ?: throw IllegalArgumentException("截图解码失败")
            activeBitmap = decoded
            val scale = minOf(
                1f,
                TARGET_EDGE.toFloat() / maxOf(decoded.width, decoded.height).toFloat(),
            )
            if (scale < 1f) {
                val scaled = decoded.scale(
                    (decoded.width * scale).toInt().coerceAtLeast(1),
                    (decoded.height * scale).toInt().coerceAtLeast(1),
                )
                decoded.recycle()
                activeBitmap = scaled
            }
            val outputFile = File(stagingDirectory, "evidence-${UUID.randomUUID()}.webp")
            prepared = outputFile
            FileOutputStream(outputFile).use { output ->
                val format = if (Build.VERSION.SDK_INT >= 30) {
                    Bitmap.CompressFormat.WEBP_LOSSY
                } else {
                    legacyWebpFormat()
                }
                check(requireNotNull(activeBitmap).compress(format, 88, output)) { "截图压缩失败" }
            }
            require(outputFile.length() in 1..MAX_SOURCE_BYTES) { "截图压缩后仍然过大" }
            completed = true
            return outputFile
        } finally {
            activeBitmap?.takeUnless(Bitmap::isRecycled)?.recycle()
            original.delete()
            if (!completed) prepared?.delete()
        }
    }

    private fun openSource(source: Uri): InputStream? = when (source.scheme) {
        "file" -> source.path?.let { File(it).takeIf(File::isFile)?.inputStream() }
        else -> context.contentResolver.openInputStream(source)
    }

    private fun draftDirectory(userId: String): File =
        File(context.filesDir, "bug-drafts/${safeSegment(userId)}")

    private fun safeSegment(value: String): String = value.replace(Regex("[^A-Za-z0-9._-]"), "_")

    @Suppress("DEPRECATION")
    private fun legacyWebpFormat(): Bitmap.CompressFormat = Bitmap.CompressFormat.WEBP

    private companion object {
        const val MAX_SOURCE_BYTES = 10L * 1024L * 1024L
        const val MAX_DECODE_PIXELS = 4_000_000L
        const val TARGET_EDGE = 2560
    }
}
