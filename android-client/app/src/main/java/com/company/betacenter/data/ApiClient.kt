package com.company.betacenter.data

import android.os.Build
import com.company.betacenter.BuildConfig
import com.company.betacenter.security.SecureSessionStore
import com.company.betacenter.security.SessionSnapshot
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Call
import okhttp3.Callback
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import org.json.JSONObject
import java.io.BufferedInputStream
import java.io.BufferedOutputStream
import java.io.File
import java.io.InputStream
import java.io.IOException
import java.io.Closeable
import java.net.HttpURLConnection
import java.net.URI
import java.net.URLEncoder
import java.nio.charset.StandardCharsets
import java.util.UUID
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicReference

internal class DownloadCallResources {
    private val cancelled = AtomicBoolean(false)
    private val connection = AtomicReference<HttpURLConnection?>()
    private val input = AtomicReference<Closeable?>()
    private val output = AtomicReference<Closeable?>()

    val isCancelled: Boolean get() = cancelled.get()

    fun attachConnection(value: HttpURLConnection) {
        connection.set(value)
        if (cancelled.get() && connection.compareAndSet(value, null)) runCatching(value::disconnect)
        throwIfCancelled()
    }

    fun attachInput(value: Closeable) = attach(input, value)
    fun attachOutput(value: Closeable) = attach(output, value)
    fun detachInput(value: Closeable) = input.compareAndSet(value, null)
    fun detachOutput(value: Closeable) = output.compareAndSet(value, null)

    fun cancel() {
        cancelled.set(true)
        release()
    }

    fun release() {
        output.getAndSet(null)?.let { runCatching(it::close) }
        input.getAndSet(null)?.let { runCatching(it::close) }
        connection.getAndSet(null)?.let { runCatching(it::disconnect) }
    }

    fun throwIfCancelled() {
        if (cancelled.get()) throw CancellationException("APK 下载已取消")
    }

    private fun attach(reference: AtomicReference<Closeable?>, value: Closeable) {
        reference.set(value)
        if (cancelled.get() && reference.compareAndSet(value, null)) runCatching(value::close)
        throwIfCancelled()
    }
}

data class MultipartFilePart(
    val filename: String,
    val contentType: String,
    val length: Long,
    val openStream: () -> InputStream,
)

class ApiClient(
    private val sessionStore: SecureSessionStore,
    baseUrl: String = BuildConfig.API_BASE_URL,
) {
    private val origin = URI(baseUrl.trimEnd('/') + "/")
    private val refreshMutex = Mutex()
    private val extendedHttpClient = OkHttpClient.Builder()
        .connectTimeout(CONNECT_TIMEOUT_MILLIS.toLong(), TimeUnit.MILLISECONDS)
        .readTimeout(READ_TIMEOUT_MILLIS.toLong(), TimeUnit.MILLISECONDS)
        .followRedirects(false)
        .followSslRedirects(false)
        .build()

    suspend fun login(phone: String, password: String): AuthSession {
        val expected = sessionStore.snapshot()
        return withContext(Dispatchers.IO) {
            val body = JSONObject()
                .put("phone", phone.trim())
                .put("password", password)
                .put("client_name", "android-${BuildConfig.VERSION_NAME}")
            val response = try {
                request("POST", "/api/v1/auth/login", jsonBody = body)
            } catch (exception: Exception) {
                ensureSnapshotUnchanged(expected)
                throw exception
            }
            requireSuccess(response)
            val session = parseSession(response.jsonObject())
            sessionStore.beginSessionIfUnchanged(expected, session)?.session ?: throw sessionChanged()
        }
    }

    fun clearLocalSession(): String? = sessionStore.clearAndAdvance().session?.accessToken

    fun markLocalSessionRetiring(): AuthSession? = sessionStore.retireCurrent()?.session

    fun retiringSession(): AuthSession? = sessionStore.loadRetiring()

    suspend fun revokeSession(accessToken: String?): Unit = withContext(Dispatchers.IO) {
        if (accessToken.isNullOrBlank()) return@withContext
        runCatching { request("POST", "/api/v1/auth/logout", bearerToken = accessToken) }
        Unit
    }

    suspend fun changePassword(currentPassword: String, newPassword: String) {
        val initial = sessionStore.snapshot()
        val initialSession = initial.session ?: throw notAuthenticated()
        withContext(Dispatchers.IO) {
            val body = JSONObject()
                .put("current_password", currentPassword)
                .put("new_password", newPassword)
            val response = authenticatedRequest(initial, "POST", "/api/v1/auth/change-password", body)
            requireSuccess(response)
            if (!sessionStore.clearGenerationIfCurrent(initial.generation, initialSession.user.id)) {
                throw sessionChanged()
            }
        }
    }

    suspend fun listApps(search: String = ""): List<AppCard> {
        val initial = sessionStore.snapshot()
        return withContext(Dispatchers.IO) {
            val query = if (search.isBlank()) "" else "?search=${encode(search.trim())}"
            val response = authenticatedRequest(initial, "GET", "/api/v1/apps$query")
            requireSuccess(response)
            parseApps(response.jsonArray())
        }
    }

    suspend fun getApp(appId: String): AppDetails {
        val initial = sessionStore.snapshot()
        return withContext(Dispatchers.IO) {
            val response = authenticatedRequest(initial, "GET", "/api/v1/apps/${encodePath(appId)}")
            requireSuccess(response)
            parseAppDetails(response.jsonObject())
        }
    }

    suspend fun listBugs(
        mine: Boolean = false,
        appId: String? = null,
        status: BugState? = null,
        page: Int = 1,
        pageSize: Int = 20,
    ): BugPage {
        val initial = sessionStore.snapshot()
        return withContext(Dispatchers.IO) {
            val parameters = buildList {
                add("mine=$mine")
                appId?.let { add("app_id=${encode(it)}") }
                status?.takeUnless { it == BugState.UNKNOWN }?.let { add("status=${encode(it.wireValue)}") }
                add("page=$page")
                add("page_size=$pageSize")
            }.joinToString("&")
            val response = authenticatedRequest(initial, "GET", "/api/v1/bugs?$parameters")
            requireSuccess(response)
            parseBugPage(response.jsonObject())
        }
    }

    suspend fun getBug(bugId: String): BugReport {
        val initial = sessionStore.snapshot()
        return withContext(Dispatchers.IO) {
            val response = authenticatedRequest(initial, "GET", "/api/v1/bugs/${encodePath(bugId)}")
            requireSuccess(response)
            parseBug(response.jsonObject())
        }
    }

    suspend fun updateBugText(bugId: String, update: BugTextUpdate): BugReport {
        val initial = sessionStore.snapshot()
        return withContext(Dispatchers.IO) {
            val response = authenticatedRequest(
                initial,
                "PATCH",
                "/api/v1/bugs/${encodePath(bugId)}",
                bugTextUpdateJson(update),
            )
            requireSuccess(response)
            parseBug(response.jsonObject())
        }
    }

    suspend fun addBugComment(bugId: String, content: String): BugReport {
        val initial = sessionStore.snapshot()
        return withContext(Dispatchers.IO) {
            val response = authenticatedRequest(
                initial,
                "POST",
                "/api/v1/bugs/${encodePath(bugId)}/comments",
                JSONObject().put("content", content.trim()),
            )
            requireSuccess(response)
            parseBug(response.jsonObject())
        }
    }

    suspend fun verifyBug(bugId: String, accepted: Boolean, note: String): BugReport {
        val initial = sessionStore.snapshot()
        return withContext(Dispatchers.IO) {
            val response = authenticatedRequest(
                initial,
                "POST",
                "/api/v1/bugs/${encodePath(bugId)}/verification",
                JSONObject().put("accepted", accepted).put("note", note.trim()),
            )
            requireSuccess(response)
            parseBug(response.jsonObject())
        }
    }

    suspend fun createBug(
        fields: Map<String, String>,
        files: List<MultipartFilePart>,
    ): BugReport {
        val initial = sessionStore.snapshot()
        return withContext(Dispatchers.IO) {
            require(files.size <= 5) { "Bug 截图最多 5 张" }
            var session = ensureFreshSession(initial)
            var response = requestForSession(session) {
                requestMultipart("/api/v1/bugs", fields, files, requireNotNull(session.session).accessToken)
            }
            if (response.status == HttpURLConnection.HTTP_UNAUTHORIZED) {
                session = refreshAfterUnauthorized(session)
                response = requestForSession(session) {
                    requestMultipart("/api/v1/bugs", fields, files, requireNotNull(session.session).accessToken)
                }
                if (response.status == HttpURLConnection.HTTP_UNAUTHORIZED) {
                    if (!sessionStore.clearIfCurrent(session)) throw sessionChanged()
                    throw notAuthenticated()
                }
            }
            ensureCurrentGeneration(session)
            requireSuccess(response)
            parseBug(response.jsonObject())
        }
    }

    suspend fun loadPrivateImage(relativeUrl: String): ByteArray {
        val initial = sessionStore.snapshot()
        return withContext(Dispatchers.IO) {
            val response = authenticatedRequest(initial, "GET", relativeUrl, maxResponseBytes = MAX_IMAGE_BYTES)
            requireSuccess(response)
            response.body
        }
    }

    suspend fun startDownload(versionId: String, clientRequestId: String): DownloadTicket {
        val initial = sessionStore.snapshot()
        return withContext(Dispatchers.IO) {
            val body = JSONObject()
                .put("version_id", versionId)
                .put("client_request_id", clientRequestId)
                .put("device_model", deviceModel())
                .put("android_version", Build.VERSION.RELEASE.orEmpty())
                .put("client_version", BuildConfig.VERSION_NAME)
            val response = authenticatedRequest(initial, "POST", "/api/v1/downloads", body)
            requireSuccess(response)
            parseDownloadTicket(response.jsonObject())
        }
    }

    suspend fun downloadFile(
        ticket: DownloadTicket,
        destinationPart: File,
        onProgress: (bytes: Long, total: Long) -> Unit,
    ): Long {
        val initial = sessionStore.snapshot()
        return withContext(Dispatchers.IO) {
            var session = ensureFreshSession(initial)
            var outcome = downloadAttempt(
                ticket,
                destinationPart,
                requireNotNull(session.session).accessToken,
                onProgress,
            )
            if (outcome == DownloadOutcome.Unauthorized) {
                session = refreshAfterUnauthorized(session)
                outcome = downloadAttempt(
                    ticket,
                    destinationPart,
                    requireNotNull(session.session).accessToken,
                    onProgress,
                )
            }
            ensureCurrentGeneration(session)
            when (outcome) {
                is DownloadOutcome.Complete -> outcome.bytes
                is DownloadOutcome.Failure -> throw outcome.exception
                DownloadOutcome.Unauthorized -> {
                    if (!sessionStore.clearIfCurrent(session)) throw sessionChanged()
                    throw notAuthenticated()
                }
            }
        }
    }

    suspend fun completeDownload(downloadId: String, sha256: String, bytesReceived: Long) {
        val initial = sessionStore.snapshot()
        withContext(Dispatchers.IO) {
            val response = authenticatedRequest(
                initial,
                "POST",
                "/api/v1/downloads/${encodePath(downloadId)}/complete",
                JSONObject().put("sha256", sha256).put("bytes_received", bytesReceived),
            )
            requireSuccess(response)
        }
    }

    suspend fun failDownload(downloadId: String, reason: String, cancelled: Boolean = false) {
        val initial = sessionStore.snapshot()
        withContext(Dispatchers.IO) {
            val response = authenticatedRequest(
                initial,
                "POST",
                "/api/v1/downloads/${encodePath(downloadId)}/failure",
                JSONObject()
                    .put("status", if (cancelled) "cancelled" else "failed")
                    .put("reason", reason.take(300)),
            )
            requireSuccess(response)
        }
    }

    fun currentSession(): AuthSession? = sessionStore.load()

    internal fun currentDownloadSession(): AuthSession? = sessionStore.loadRaw()

    private suspend fun authenticatedRequest(
        initial: SessionSnapshot,
        method: String,
        relativeUrl: String,
        body: JSONObject? = null,
        maxResponseBytes: Int = MAX_JSON_BYTES,
    ): RawResponse {
        var session = ensureFreshSession(initial)
        var response = requestForSession(session) {
            request(
                method,
                relativeUrl,
                body,
                requireNotNull(session.session).accessToken,
                maxResponseBytes,
            )
        }
        if (response.status == HttpURLConnection.HTTP_UNAUTHORIZED) {
            session = refreshAfterUnauthorized(session)
            response = requestForSession(session) {
                request(
                    method,
                    relativeUrl,
                    body,
                    requireNotNull(session.session).accessToken,
                    maxResponseBytes,
                )
            }
            if (response.status == HttpURLConnection.HTTP_UNAUTHORIZED) {
                if (!sessionStore.clearIfCurrent(session)) throw sessionChanged()
                throw notAuthenticated()
            }
        }
        ensureCurrentGeneration(session)
        return response
    }

    private suspend fun ensureFreshSession(initial: SessionSnapshot): SessionSnapshot {
        val initialSession = initial.session ?: throw notAuthenticated()
        val current = sessionStore.snapshot()
        if (current.generation != initial.generation || current.session?.user?.id != initialSession.user.id) {
            throw sessionChanged()
        }
        val currentSession = requireNotNull(current.session)
        if (currentSession.expiresAtEpochMillis > System.currentTimeMillis() + REFRESH_SKEW_MILLIS) return current
        return refreshSingleFlight(current)
    }

    private suspend fun refreshAfterUnauthorized(failed: SessionSnapshot): SessionSnapshot =
        refreshSingleFlight(failed)

    private suspend fun refreshSingleFlight(failed: SessionSnapshot): SessionSnapshot = refreshMutex.withLock {
        val failedSession = failed.session ?: throw notAuthenticated()
        val latest = sessionStore.snapshot()
        if (latest.generation != failed.generation || latest.session?.user?.id != failedSession.user.id) {
            throw sessionChanged()
        }
        val latestSession = requireNotNull(latest.session)
        if (
            latestSession.accessToken != failedSession.accessToken &&
            latestSession.expiresAtEpochMillis > System.currentTimeMillis() + REFRESH_SKEW_MILLIS
        ) {
            return@withLock latest
        }
        val response = requestForSession(latest) {
            request(
                "POST",
                "/api/v1/auth/refresh",
                jsonBody = JSONObject().put("refresh_token", latestSession.refreshToken),
            )
        }
        if (response.status !in 200..299) {
            val exception = response.toApiException()
            if (response.status in 400..499 && response.status !in setOf(408, 429)) {
                if (!sessionStore.clearIfCurrent(latest)) throw sessionChanged()
            } else {
                ensureCurrentGeneration(latest)
            }
            throw exception
        }
        val refreshed = parseSession(response.jsonObject())
        if (refreshed.user.id != latestSession.user.id) {
            if (!sessionStore.clearIfCurrent(latest)) throw sessionChanged()
            throw ApiException(502, "session_identity_mismatch", "服务器返回了不匹配的登录账户")
        }
        sessionStore.refreshIfCurrent(latest, refreshed) ?: throw sessionChanged()
    }

    private suspend inline fun <T> requestForSession(
        session: SessionSnapshot,
        requestBlock: suspend () -> T,
    ): T =
        try {
            requestBlock()
        } catch (exception: Exception) {
            ensureCurrentGeneration(session)
            throw exception
        }

    private fun ensureSnapshotUnchanged(expected: SessionSnapshot) {
        if (sessionStore.snapshot() != expected) throw sessionChanged()
    }

    private fun ensureCurrentGeneration(expected: SessionSnapshot): SessionSnapshot {
        val expectedUser = expected.session?.user?.id ?: throw notAuthenticated()
        val current = sessionStore.snapshot()
        if (current.generation != expected.generation || current.session?.user?.id != expectedUser) {
            throw sessionChanged()
        }
        return current
    }

    private fun notAuthenticated(): ApiException =
        ApiException(401, "not_authenticated", "登录状态已失效，请重新登录")

    private fun sessionChanged(): ApiException =
        ApiException(409, "session_changed", "登录账户已变化，请重新执行操作")

    private suspend fun request(
        method: String,
        relativeUrl: String,
        jsonBody: JSONObject? = null,
        bearerToken: String? = null,
        maxResponseBytes: Int = MAX_JSON_BYTES,
    ): RawResponse {
        val bytes = jsonBody?.toString()?.toByteArray(StandardCharsets.UTF_8)
        if (usesExtendedHttpTransport(method)) {
            return requestExtended(method, relativeUrl, bytes, bearerToken, maxResponseBytes)
        }
        val connection = openConnection(relativeUrl).apply {
            requestMethod = method
            connectTimeout = CONNECT_TIMEOUT_MILLIS
            readTimeout = READ_TIMEOUT_MILLIS
            instanceFollowRedirects = false
            setRequestProperty("Accept", "application/json")
            setRequestProperty("User-Agent", USER_AGENT)
            bearerToken?.let { setRequestProperty("Authorization", "Bearer $it") }
            if (bytes != null) {
                doOutput = true
                setRequestProperty("Content-Type", "application/json; charset=utf-8")
                setFixedLengthStreamingMode(bytes.size)
            }
        }
        return try {
            bytes?.let { connection.outputStream.use { output -> output.write(it) } }
            connection.readResponse(maxResponseBytes)
        } finally {
            connection.disconnect()
        }
    }

    private suspend fun requestExtended(
        method: String,
        relativeUrl: String,
        body: ByteArray?,
        bearerToken: String?,
        maxResponseBytes: Int,
    ): RawResponse {
        val target = resolveSameOrigin(origin, relativeUrl)
        val request = Request.Builder()
            .url(target.toString())
            .header("Accept", "application/json")
            .header("User-Agent", USER_AGENT)
            .apply {
                bearerToken?.let { header("Authorization", "Bearer $it") }
            }
            .method(
                method,
                body?.toRequestBody("application/json; charset=utf-8".toMediaType()),
            )
            .build()
        return awaitOkHttpCall(extendedHttpClient.newCall(request)) { response ->
            response.use {
                val responseBody = it.body.byteStream().use { stream -> stream.readLimited(maxResponseBytes) }
                RawResponse(it.code, responseBody, it.headers.toMultimap())
            }
        }
    }

    private fun requestMultipart(
        relativeUrl: String,
        fields: Map<String, String>,
        files: List<MultipartFilePart>,
        bearerToken: String,
    ): RawResponse {
        val boundary = "BetaCenter-${UUID.randomUUID()}"
        val connection = openConnection(relativeUrl).apply {
            requestMethod = "POST"
            connectTimeout = CONNECT_TIMEOUT_MILLIS
            readTimeout = UPLOAD_TIMEOUT_MILLIS
            instanceFollowRedirects = false
            doOutput = true
            setChunkedStreamingMode(STREAM_BUFFER_BYTES)
            setRequestProperty("Accept", "application/json")
            setRequestProperty("Authorization", "Bearer $bearerToken")
            setRequestProperty("Content-Type", "multipart/form-data; boundary=$boundary")
            setRequestProperty("User-Agent", USER_AGENT)
        }
        return try {
            BufferedOutputStream(connection.outputStream, STREAM_BUFFER_BYTES).use { output ->
                fields.forEach { (name, value) ->
                    output.writeUtf8("--$boundary\r\n")
                    output.writeUtf8("Content-Disposition: form-data; name=\"${headerSafe(name)}\"\r\n")
                    output.writeUtf8("Content-Type: text/plain; charset=utf-8\r\n\r\n")
                    output.write(value.toByteArray(StandardCharsets.UTF_8))
                    output.writeUtf8("\r\n")
                }
                files.forEach { file ->
                    output.writeUtf8("--$boundary\r\n")
                    output.writeUtf8(
                        "Content-Disposition: form-data; name=\"files\"; filename=\"${headerSafe(file.filename)}\"\r\n",
                    )
                    output.writeUtf8("Content-Type: ${file.contentType}\r\n\r\n")
                    file.openStream().use { input -> input.copyTo(output, STREAM_BUFFER_BYTES) }
                    output.writeUtf8("\r\n")
                }
                output.writeUtf8("--$boundary--\r\n")
            }
            connection.readResponse(MAX_JSON_BYTES)
        } finally {
            connection.disconnect()
        }
    }

    private suspend fun downloadAttempt(
        ticket: DownloadTicket,
        destinationPart: File,
        bearerToken: String,
        onProgress: (Long, Long) -> Unit,
    ): DownloadOutcome = withContext(Dispatchers.IO) {
        suspendCancellableCoroutine { continuation ->
            val resources = DownloadCallResources()
            continuation.invokeOnCancellation { resources.cancel() }
            var outcome: DownloadOutcome? = null
            try {
                outcome = performDownloadAttempt(
                    ticket,
                    destinationPart,
                    bearerToken,
                    onProgress,
                    resources,
                )
            } catch (exception: Exception) {
                if (!resources.isCancelled) outcome = DownloadOutcome.Failure(exception)
            } finally {
                resources.release()
            }
            outcome?.let { completed -> continuation.resume(completed) { _, _, _ -> } }
        }
    }

    private fun performDownloadAttempt(
        ticket: DownloadTicket,
        destinationPart: File,
        bearerToken: String,
        onProgress: (Long, Long) -> Unit,
        resources: DownloadCallResources,
    ): DownloadOutcome {
        resources.throwIfCancelled()
        destinationPart.parentFile?.mkdirs()
        var existing = destinationPart.takeIf(File::isFile)?.length() ?: 0L
        if (existing < 0L || existing > ticket.fileSize) {
            destinationPart.delete()
            existing = 0L
        }
        if (existing == ticket.fileSize) return DownloadOutcome.Complete(existing)

        val connection = openConnection(ticket.url).apply {
            requestMethod = "GET"
            connectTimeout = CONNECT_TIMEOUT_MILLIS
            readTimeout = DOWNLOAD_TIMEOUT_MILLIS
            instanceFollowRedirects = false
            setRequestProperty("Authorization", "Bearer $bearerToken")
            setRequestProperty("Accept", "application/vnd.android.package-archive")
            setRequestProperty("User-Agent", USER_AGENT)
            if (existing > 0L) setRequestProperty("Range", "bytes=$existing-")
        }
        resources.attachConnection(connection)
        return try {
            resources.throwIfCancelled()
            val status = connection.responseCode
            if (status == HttpURLConnection.HTTP_UNAUTHORIZED) return DownloadOutcome.Unauthorized
            if (status !in listOf(HttpURLConnection.HTTP_OK, HttpURLConnection.HTTP_PARTIAL)) {
                return DownloadOutcome.Failure(connection.readResponse(MAX_JSON_BYTES).toApiException())
            }

            val append = status == HttpURLConnection.HTTP_PARTIAL && existing > 0L
            if (status == HttpURLConnection.HTTP_PARTIAL) {
                val rangeStart = connection.getHeaderField("Content-Range")
                    ?.substringAfter("bytes ")
                    ?.substringBefore('-')
                    ?.toLongOrNull()
                if (rangeStart != existing) {
                    return DownloadOutcome.Failure(
                        ApiException(502, "invalid_content_range", "服务器返回的断点范围无效，请重试"),
                    )
                }
            } else if (existing > 0L) {
                existing = 0L
            }

            val modeAppend = append && existing > 0L
            val outputStart = if (modeAppend) existing else 0L
            var received = outputStart
            val input = BufferedInputStream(connection.inputStream, STREAM_BUFFER_BYTES)
            resources.attachInput(input)
            try {
                input.use {
                    val output = java.io.FileOutputStream(destinationPart, modeAppend).buffered(STREAM_BUFFER_BYTES)
                    resources.attachOutput(output)
                    try {
                        output.use {
                            val buffer = ByteArray(STREAM_BUFFER_BYTES)
                            while (true) {
                                resources.throwIfCancelled()
                                val count = input.read(buffer)
                                if (count < 0) break
                                resources.throwIfCancelled()
                                output.write(buffer, 0, count)
                                received += count
                                if (received > ticket.fileSize) {
                                    throw ApiException(
                                        422,
                                        "download_size_mismatch",
                                        "下载文件大小与服务端记录不一致",
                                    )
                                }
                                onProgress(received, ticket.fileSize)
                            }
                        }
                    } finally {
                        resources.detachOutput(output)
                    }
                }
            } finally {
                resources.detachInput(input)
            }
            if (received != ticket.fileSize) throw IOException("下载连接提前结束")
            DownloadOutcome.Complete(received)
        } finally {
            resources.release()
        }
    }

    private fun openConnection(relativeUrl: String): HttpURLConnection {
        val target = resolveSameOrigin(origin, relativeUrl)
        return target.toURL().openConnection() as HttpURLConnection
    }

    private fun HttpURLConnection.readResponse(limit: Int): RawResponse {
        val status = responseCode
        val stream = if (status in 200..299) inputStream else errorStream
        val body = stream?.use { it.readLimited(limit) } ?: ByteArray(0)
        val headers = headerFields.mapNotNull { (key, value) -> key?.let { it to value } }.toMap()
        return RawResponse(status, body, headers)
    }

    private fun InputStream.readLimited(limit: Int): ByteArray {
        val output = java.io.ByteArrayOutputStream(minOf(limit, 64 * 1024))
        val buffer = ByteArray(16 * 1024)
        var total = 0
        while (true) {
            val count = read(buffer)
            if (count < 0) break
            total += count
            if (total > limit) throw ApiException(502, "response_too_large", "服务器响应过大")
            output.write(buffer, 0, count)
        }
        return output.toByteArray()
    }

    private fun requireSuccess(response: RawResponse) {
        if (response.status !in 200..299) throw response.toApiException()
    }

    private fun RawResponse.toApiException(): ApiException {
        val parsed = runCatching { jsonObject().optJSONObject("error") }.getOrNull()
        val fallback = when (status) {
            401 -> "登录状态已失效，请重新登录"
            403 -> "你没有执行此操作的权限"
            404 -> "内容不存在或已不可见"
            413 -> "上传内容过大，请减少截图后重试"
            429 -> "操作过于频繁，请稍后再试"
            in 500..599 -> "服务暂时不可用，请稍后重试"
            else -> "请求未完成，请检查后重试"
        }
        return ApiException(
            statusCode = status,
            errorCode = parsed?.optString("code").orEmpty().ifBlank { "http_$status" },
            message = parsed?.optString("message").orEmpty().ifBlank { fallback },
            requestId = parsed?.optString("request_id")?.takeIf(String::isNotBlank),
        )
    }

    private fun RawResponse.jsonObject(): JSONObject = JSONObject(body.toString(StandardCharsets.UTF_8))
    private fun RawResponse.jsonArray() = org.json.JSONArray(body.toString(StandardCharsets.UTF_8))

    private fun BufferedOutputStream.writeUtf8(value: String) = write(value.toByteArray(StandardCharsets.UTF_8))

    private fun headerSafe(value: String): String = value.replace(Regex("[\\r\\n\\\"]"), "_")
    private fun encode(value: String): String = URLEncoder.encode(value, StandardCharsets.UTF_8.name())
    private fun encodePath(value: String): String = encode(value).replace("+", "%20")
    private fun deviceModel(): String = listOf(Build.MANUFACTURER, Build.MODEL).joinToString(" ").trim().take(120)

    private data class RawResponse(
        val status: Int,
        val body: ByteArray,
        val headers: Map<String, List<String>>,
    )

    private sealed interface DownloadOutcome {
        data class Complete(val bytes: Long) : DownloadOutcome
        data class Failure(val exception: Exception) : DownloadOutcome
        data object Unauthorized : DownloadOutcome
    }

    private companion object {
        const val CONNECT_TIMEOUT_MILLIS = 15_000
        const val READ_TIMEOUT_MILLIS = 60_000
        const val UPLOAD_TIMEOUT_MILLIS = 120_000
        const val DOWNLOAD_TIMEOUT_MILLIS = 120_000
        const val REFRESH_SKEW_MILLIS = 30_000L
        const val STREAM_BUFFER_BYTES = 64 * 1024
        const val MAX_JSON_BYTES = 4 * 1024 * 1024
        const val MAX_IMAGE_BYTES = 12 * 1024 * 1024
        const val USER_AGENT = "BetaCenter-Android/1"
    }
}

internal fun resolveSameOrigin(origin: URI, reference: String): URI {
    val target = origin.resolve(reference)
    val sameOrigin =
        target.scheme.equals(origin.scheme, ignoreCase = true) &&
            target.host.equals(origin.host, ignoreCase = true) &&
            effectiveNetworkPort(target) == effectiveNetworkPort(origin) &&
            target.userInfo == null
    require(sameOrigin) { "拒绝访问非平台地址" }
    return target
}

internal fun usesExtendedHttpTransport(method: String): Boolean = method == "PATCH"

internal suspend fun <T> awaitOkHttpCall(call: Call, readResponse: (Response) -> T): T =
    suspendCancellableCoroutine { continuation ->
        continuation.invokeOnCancellation { call.cancel() }
        call.enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                continuation.resumeWith(Result.failure(e))
            }

            override fun onResponse(call: Call, response: Response) {
                if (!continuation.isActive) {
                    response.close()
                    return
                }
                val result = runCatching { readResponse(response) }
                continuation.resumeWith(result)
            }
        })
    }

internal fun bugTextUpdateJson(update: BugTextUpdate): JSONObject = JSONObject()
    .put("title", update.title)
    .put("description", update.description)
    .put("reproduction_steps", update.reproductionSteps)

private fun effectiveNetworkPort(uri: URI): Int = when {
    uri.port != -1 -> uri.port
    uri.scheme.equals("https", ignoreCase = true) -> 443
    else -> 80
}
