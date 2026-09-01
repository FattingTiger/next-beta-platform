package com.company.betacenter.update

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.company.betacenter.BuildConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

class ClientUpdateManager(private val context: Context) {
    private val preferences = context.getSharedPreferences(PREFERENCES_NAME, Context.MODE_PRIVATE)
    private val httpClient = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .followRedirects(false)
        .followSslRedirects(false)
        .build()
    private val _availableUpdate = MutableStateFlow(readStoredUpdate())
    val availableUpdate: StateFlow<ClientUpdate?> = _availableUpdate.asStateFlow()
    private val checkMutex = Mutex()

    init {
        if (_availableUpdate.value?.versionCode?.let { it <= BuildConfig.VERSION_CODE } == true) {
            storeUpdate(null)
        }
    }

    fun scheduleWeeklyChecks() {
        val constraints = Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()
        val periodicRequest = PeriodicWorkRequestBuilder<ClientUpdateCheckWorker>(
            7,
            TimeUnit.DAYS,
            1,
            TimeUnit.DAYS,
        )
            .setConstraints(constraints)
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
            .build()
        val workManager = WorkManager.getInstance(context)
        workManager.enqueueUniquePeriodicWork(
            UNIQUE_PERIODIC_WORK,
            ExistingPeriodicWorkPolicy.KEEP,
            periodicRequest,
        )
        val lastCheckedAt = preferences.getLong(KEY_LAST_CHECKED_AT, 0L)
        if (System.currentTimeMillis() - lastCheckedAt >= WEEK_MILLIS) {
            val immediateRequest = OneTimeWorkRequestBuilder<ClientUpdateCheckWorker>()
                .setConstraints(constraints)
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
                .build()
            workManager.enqueueUniqueWork(
                UNIQUE_DUE_WORK,
                ExistingWorkPolicy.KEEP,
                immediateRequest,
            )
        }
    }

    suspend fun checkForUpdate(): ClientUpdate? = checkMutex.withLock {
        val lastCheckedAt = preferences.getLong(KEY_LAST_CHECKED_AT, 0L)
        if (System.currentTimeMillis() - lastCheckedAt < DUPLICATE_CHECK_WINDOW_MILLIS) {
            return@withLock _availableUpdate.value
        }
        withContext(Dispatchers.IO) {
            val request = Request.Builder()
                .url(updateIndexUrl())
                .header("Accept", "application/json")
                .get()
                .build()
            val index = httpClient.newCall(request).execute().use { response ->
                if (!response.isSuccessful) throw IOException("更新检查失败：HTTP ${response.code}")
                val body = response.body
                val declaredLength = body.contentLength()
                if (declaredLength > MAX_INDEX_BYTES) throw IOException("更新清单过大")
                body.string().also {
                    if (it.toByteArray().size > MAX_INDEX_BYTES) throw IOException("更新清单过大")
                }
            }
            val entry = selectNewerClientUpdate(
                entries = parseUpdateIndex(index),
                installedVersionName = BuildConfig.VERSION_NAME,
                installedVersionCode = BuildConfig.VERSION_CODE,
            )
            val update = entry?.let {
                ClientUpdate(
                    fileName = it.fileName,
                    version = it.version,
                    versionCode = it.versionCode,
                    sha256 = it.sha256,
                    fileSize = it.fileSize,
                    releaseNotes = it.releaseNotes,
                    downloadUrl = updateDirectoryUrl() + it.fileName,
                )
            }
            preferences.edit().putLong(KEY_LAST_CHECKED_AT, System.currentTimeMillis()).apply()
            storeUpdate(update)
            update
        }
    }

    private fun storeUpdate(update: ClientUpdate?) {
        if (update == null) {
            preferences.edit().remove(KEY_AVAILABLE_UPDATE).apply()
            _availableUpdate.value = null
            return
        }
        val value = JSONObject()
            .put("name", update.fileName)
            .put("versionCode", update.versionCode)
            .put("sha256", update.sha256)
            .put("size", update.fileSize)
            .put("releaseNotes", update.releaseNotes)
            .toString()
        preferences.edit().putString(KEY_AVAILABLE_UPDATE, value).apply()
        _availableUpdate.value = update
    }

    private fun readStoredUpdate(): ClientUpdate? = runCatching {
        val json = preferences.getString(KEY_AVAILABLE_UPDATE, null) ?: return null
        val entry = parseUpdateIndex("{\"files\":[$json]}").singleOrNull() ?: return null
        ClientUpdate(
            fileName = entry.fileName,
            version = entry.version,
            versionCode = entry.versionCode,
            sha256 = entry.sha256,
            fileSize = entry.fileSize,
            releaseNotes = entry.releaseNotes,
            downloadUrl = updateDirectoryUrl() + entry.fileName,
        )
    }.getOrNull()

    private fun updateDirectoryUrl(): String =
        BuildConfig.API_BASE_URL.trimEnd('/') + UPDATE_DIRECTORY_PATH

    private fun updateIndexUrl(): String = updateDirectoryUrl() + UPDATE_INDEX_FILE

    companion object {
        private const val UPDATE_DIRECTORY_PATH = "/downloads/android/"
        private const val UPDATE_INDEX_FILE = "index.json"
        private const val UNIQUE_PERIODIC_WORK = "next-beta-client-update-check"
        private const val UNIQUE_DUE_WORK = "next-beta-client-update-check-due"
        private const val PREFERENCES_NAME = "next-beta-client-updates"
        private const val KEY_AVAILABLE_UPDATE = "available-update"
        private const val KEY_LAST_CHECKED_AT = "last-checked-at"
        private const val MAX_INDEX_BYTES = 256 * 1024
        private const val WEEK_MILLIS = 7L * 24L * 60L * 60L * 1_000L
        private const val DUPLICATE_CHECK_WINDOW_MILLIS = 60L * 60L * 1_000L
    }
}

class ClientUpdateCheckWorker(
    appContext: Context,
    params: WorkerParameters,
) : CoroutineWorker(appContext, params) {
    override suspend fun doWork(): Result {
        val application = applicationContext as? com.company.betacenter.BetaCenterApplication
            ?: return Result.failure()
        return try {
            application.container.clientUpdateManager.checkForUpdate()
            Result.success()
        } catch (_: IOException) {
            Result.retry()
        } catch (_: Exception) {
            Result.failure()
        }
    }
}
