package com.company.betacenter.download

import java.io.File
import java.security.MessageDigest

internal const val DOWNLOAD_ROOT_DIRECTORY = "downloads"

/**
 * Maps an opaque server user id to a path/tag-safe, fixed-width owner key.
 *
 * Hashing instead of replacing punctuation avoids collisions such as `a/b`
 * and `a_b`, and keeps account identifiers out of file paths and WorkManager
 * metadata.
 */
internal fun downloadOwnerKey(userId: String): String {
    require(userId.isNotBlank()) { "userId must not be blank" }
    return MessageDigest.getInstance("SHA-256")
        .digest(userId.toByteArray(Charsets.UTF_8))
        .joinToString("") { byte -> "%02x".format(byte) }
}

internal fun userDownloadDirectory(filesDir: File, userId: String): File =
    File(File(filesDir, DOWNLOAD_ROOT_DIRECTORY), downloadOwnerKey(userId))

internal fun isOwnedDownloadFile(filesDir: File, userId: String, path: String?): Boolean {
    if (path.isNullOrBlank()) return false
    return runCatching {
        val ownerDirectory = userDownloadDirectory(filesDir, userId).canonicalFile
        val candidate = File(path).canonicalFile
        candidate.isFile && candidate.path.startsWith(ownerDirectory.path + File.separator)
    }.getOrDefault(false)
}

/**
 * Deletes only one account's scoped directory. Direct children of the legacy
 * shared downloads directory are also removed because those files predate
 * ownership scoping and cannot be safely attributed to any account. Other
 * users' scoped directories are intentionally preserved.
 */
internal fun deleteDownloadsForUser(filesDir: File, userId: String) {
    val root = File(filesDir, DOWNLOAD_ROOT_DIRECTORY)
    userDownloadDirectory(filesDir, userId).deleteRecursively()
    root.listFiles().orEmpty()
        .filter { file -> file.isFile }
        .forEach { file -> file.delete() }
    if (root.listFiles().isNullOrEmpty()) root.delete()
}
