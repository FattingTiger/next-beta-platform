package com.company.betacenter.data

import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant

internal fun parseSession(json: JSONObject): AuthSession = AuthSession(
    accessToken = json.getString("access_token"),
    refreshToken = json.getString("refresh_token"),
    expiresAtEpochMillis = Instant.parse(json.getString("expires_at")).toEpochMilli(),
    user = parseUser(json.getJSONObject("user")),
)

internal fun parseUser(json: JSONObject): UserProfile = UserProfile(
    id = json.getString("id"),
    displayName = json.getString("display_name"),
    phone = json.getString("phone"),
    role = json.getString("role"),
    mustChangePassword = json.getBoolean("must_change_password"),
    groupIds = json.optJSONArray("group_ids").strings(),
)

internal fun parseApps(json: JSONArray): List<AppCard> = json.objects().map { item ->
    AppCard(
        id = item.getString("id"),
        name = item.getString("name"),
        packageName = item.getString("package_name"),
        shortDescription = item.optString("short_description"),
        iconUrl = item.nullableString("icon_url"),
        currentVersion = item.optJSONObject("current_version")?.let(::parseVersion),
        updatedAt = item.getString("updated_at"),
    )
}

internal fun parseAppDetails(json: JSONObject): AppDetails = AppDetails(
    id = json.getString("id"),
    name = json.getString("name"),
    packageName = json.getString("package_name"),
    shortDescription = json.optString("short_description"),
    description = json.optString("description"),
    iconUrl = json.nullableString("icon_url"),
    currentVersion = json.optJSONObject("current_version")?.let(::parseVersion),
    screenshots = json.optJSONArray("screenshots").objects().map { item ->
        AppScreenshot(
            id = item.getString("id"),
            position = item.getInt("position"),
            contentType = item.getString("content_type"),
            url = item.getString("url"),
        )
    }.sortedBy(AppScreenshot::position),
    updatedAt = json.getString("updated_at"),
)

private fun parseVersion(json: JSONObject): AppVersion = AppVersion(
    id = json.getString("id"),
    versionName = json.getString("version_name"),
    versionCode = json.getLong("version_code"),
    minSdk = json.nullableInt("min_sdk"),
    targetSdk = json.nullableInt("target_sdk"),
    fileSize = json.getLong("file_size"),
    sha256 = json.getString("sha256"),
    signingCertSha256 = json.getString("signing_cert_sha256"),
    releaseNotes = json.optString("release_notes"),
    publishedAt = json.nullableString("published_at"),
    downloadEnabled = json.getBoolean("download_enabled"),
)

internal fun parseBugPage(json: JSONObject): BugPage = BugPage(
    items = json.getJSONArray("items").objects().map(::parseBug),
    total = json.getInt("total"),
    page = json.getInt("page"),
    pageSize = json.getInt("page_size"),
)

internal fun parseBug(json: JSONObject): BugReport = BugReport(
    id = json.getString("id"),
    reference = json.getString("reference"),
    appId = json.getString("app_id"),
    appName = json.getString("app_name"),
    versionId = json.getString("version_id"),
    versionName = json.getString("version_name"),
    reporterId = json.nullableString("reporter_id"),
    reporterName = json.nullableString("reporter_name"),
    title = json.getString("title"),
    description = json.nullableString("description"),
    reproductionSteps = json.nullableString("reproduction_steps"),
    deviceModel = json.nullableString("device_model"),
    androidVersion = json.nullableString("android_version"),
    clientVersion = json.nullableString("client_version"),
    status = BugState.fromWire(json.getString("status")),
    visibility = json.getString("visibility"),
    resolution = json.nullableString("resolution"),
    resolutionNote = json.optString("resolution_note"),
    fixVersionId = json.nullableString("fix_version_id"),
    attachments = json.optJSONArray("attachments").objects().map { item ->
        BugAttachment(
            id = item.getString("id"),
            contentType = item.getString("content_type"),
            fileSize = item.getLong("file_size"),
            url = item.getString("url"),
        )
    },
    comments = json.optJSONArray("comments").objects().map { item ->
        BugComment(
            id = item.getString("id"),
            authorName = item.getString("author_name"),
            content = item.getString("content"),
            createdAt = item.getString("created_at"),
        )
    },
    transitions = json.optJSONArray("transitions").objects().map { item ->
        BugTransition(
            id = item.getString("id"),
            actorName = item.getString("actor_name"),
            fromStatus = item.nullableString("from_status")?.let(BugState::fromWire),
            toStatus = BugState.fromWire(item.getString("to_status")),
            note = item.optString("note"),
            createdAt = item.getString("created_at"),
        )
    },
    createdAt = json.getString("created_at"),
    updatedAt = json.getString("updated_at"),
)

internal fun parseDownloadTicket(json: JSONObject): DownloadTicket = DownloadTicket(
    downloadId = json.getString("download_id"),
    clientRequestId = json.getString("client_request_id"),
    url = json.getString("url"),
    fileSize = json.getLong("file_size"),
    sha256 = json.getString("sha256"),
    filename = json.getString("filename"),
)

internal fun sessionToJson(session: AuthSession): JSONObject = JSONObject().apply {
    put("access_token", session.accessToken)
    put("refresh_token", session.refreshToken)
    put("expires_at_millis", session.expiresAtEpochMillis)
    put("user", JSONObject().apply {
        put("id", session.user.id)
        put("display_name", session.user.displayName)
        put("phone", session.user.phone)
        put("role", session.user.role)
        put("must_change_password", session.user.mustChangePassword)
        put("group_ids", JSONArray(session.user.groupIds))
    })
}

internal fun storedSessionFromJson(json: JSONObject): AuthSession = AuthSession(
    accessToken = json.getString("access_token"),
    refreshToken = json.getString("refresh_token"),
    expiresAtEpochMillis = json.getLong("expires_at_millis"),
    user = parseUser(json.getJSONObject("user")),
)

private fun JSONObject.nullableString(key: String): String? =
    if (!has(key) || isNull(key)) null else getString(key)

private fun JSONObject.nullableInt(key: String): Int? =
    if (!has(key) || isNull(key)) null else getInt(key)

private fun JSONArray?.objects(): List<JSONObject> = buildList {
    val source = this@objects ?: return@buildList
    for (index in 0 until source.length()) add(source.getJSONObject(index))
}

private fun JSONArray?.strings(): List<String> = buildList {
    val source = this@strings ?: return@buildList
    for (index in 0 until source.length()) add(source.getString(index))
}
