package com.company.betacenter.download

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.nio.file.Files

class DownloadOwnershipTest {
    @Test
    fun `owner key is stable path-safe and collision resistant for punctuation`() {
        val first = downloadOwnerKey("account/../one")

        assertEquals(first, downloadOwnerKey("account/../one"))
        assertTrue(first.matches(Regex("[0-9a-f]{64}")))
        assertNotEquals(first, downloadOwnerKey("account___one"))
        assertFalse(first.contains("account"))
    }

    @Test
    fun `user directory remains below downloads root`() {
        withTemporaryDirectory { filesDir ->
            val root = File(filesDir, DOWNLOAD_ROOT_DIRECTORY).canonicalFile
            val directory = userDownloadDirectory(filesDir, "../../another-user").canonicalFile

            assertEquals(root, directory.parentFile)
        }
    }

    @Test
    fun `cleanup removes selected owner and legacy files but preserves another owner`() {
        withTemporaryDirectory { filesDir ->
            val selected = userDownloadDirectory(filesDir, "selected-user").apply { mkdirs() }
            val another = userDownloadDirectory(filesDir, "another-user").apply { mkdirs() }
            File(selected, "selected.apk").writeText("selected")
            val anotherApk = File(another, "another.apk").apply { writeText("another") }
            val legacyApk = File(File(filesDir, DOWNLOAD_ROOT_DIRECTORY), "legacy.apk").apply {
                writeText("legacy")
            }

            deleteDownloadsForUser(filesDir, "selected-user")

            assertFalse(selected.exists())
            assertFalse(legacyApk.exists())
            assertTrue(anotherApk.isFile)
        }
    }

    @Test
    fun `owned file check rejects legacy and another account paths`() {
        withTemporaryDirectory { filesDir ->
            val ownerFile = File(userDownloadDirectory(filesDir, "owner").apply { mkdirs() }, "app.apk")
                .apply { writeText("owner") }
            val otherFile = File(userDownloadDirectory(filesDir, "other").apply { mkdirs() }, "app.apk")
                .apply { writeText("other") }
            val legacyFile = File(File(filesDir, DOWNLOAD_ROOT_DIRECTORY), "legacy.apk")
                .apply { writeText("legacy") }

            assertTrue(isOwnedDownloadFile(filesDir, "owner", ownerFile.path))
            assertFalse(isOwnedDownloadFile(filesDir, "owner", otherFile.path))
            assertFalse(isOwnedDownloadFile(filesDir, "owner", legacyFile.path))
            assertFalse(isOwnedDownloadFile(filesDir, "owner", null))
        }
    }

    private fun withTemporaryDirectory(block: (File) -> Unit) {
        val directory = Files.createTempDirectory("download-ownership-test").toFile()
        try {
            block(directory)
        } finally {
            directory.deleteRecursively()
        }
    }
}
