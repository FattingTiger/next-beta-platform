package com.company.betacenter.update

import org.json.JSONObject

data class ClientVersion(
    val major: Int,
    val minor: Int,
    val patch: Int,
) : Comparable<ClientVersion> {
    override fun compareTo(other: ClientVersion): Int =
        compareValuesBy(this, other, ClientVersion::major, ClientVersion::minor, ClientVersion::patch)

    override fun toString(): String = "$major.$minor.$patch"
}

data class ClientUpdate(
    val fileName: String,
    val version: ClientVersion,
    val versionCode: Int,
    val sha256: String,
    val fileSize: Long,
    val releaseNotes: String,
    val downloadUrl: String,
)

internal data class ClientUpdateEntry(
    val fileName: String,
    val version: ClientVersion,
    val versionCode: Int,
    val sha256: String,
    val fileSize: Long,
    val releaseNotes: String,
)

private val apkFilePattern = Regex("^NEXT-Beta-android-(\\d+)\\.(\\d+)\\.(\\d+)\\.apk$")
private val appVersionPattern = Regex("^(\\d+)\\.(\\d+)\\.(\\d+)")
private val sha256Pattern = Regex("^[0-9a-f]{64}$")

internal fun parseApkFileVersion(fileName: String): ClientVersion? =
    apkFilePattern.matchEntire(fileName)?.toClientVersion()

internal fun parseInstalledClientVersion(versionName: String): ClientVersion? =
    appVersionPattern.find(versionName)?.toClientVersion()

private fun MatchResult.toClientVersion(): ClientVersion? = runCatching {
    ClientVersion(
        major = groupValues[1].toInt(),
        minor = groupValues[2].toInt(),
        patch = groupValues[3].toInt(),
    )
}.getOrNull()

internal fun parseUpdateIndex(json: String): List<ClientUpdateEntry> {
    val files = JSONObject(json).optJSONArray("files") ?: return emptyList()
    return buildList {
        for (index in 0 until files.length()) {
            val item = files.optJSONObject(index) ?: continue
            val fileName = item.optString("name")
            val version = parseApkFileVersion(fileName) ?: continue
            val versionCode = item.optInt("versionCode", -1)
            val sha256 = item.optString("sha256").lowercase()
            val fileSize = item.optLong("size", -1L)
            if (versionCode <= 0 || !sha256Pattern.matches(sha256) || fileSize <= 0L) continue
            add(
                ClientUpdateEntry(
                    fileName = fileName,
                    version = version,
                    versionCode = versionCode,
                    sha256 = sha256,
                    fileSize = fileSize,
                    releaseNotes = item.optString("releaseNotes").trim().take(1_000),
                ),
            )
        }
    }
}

internal fun selectNewerClientUpdate(
    entries: List<ClientUpdateEntry>,
    installedVersionName: String,
    installedVersionCode: Int,
): ClientUpdateEntry? {
    val installedVersion = parseInstalledClientVersion(installedVersionName) ?: return null
    return entries
        .asSequence()
        .filter { it.version > installedVersion && it.versionCode > installedVersionCode }
        .maxWithOrNull(compareBy<ClientUpdateEntry>({ it.version }, { it.versionCode }))
}
