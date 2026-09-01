package com.company.betacenter.update

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ClientUpdatePolicyTest {
    @Test
    fun `APK filename contains the version used for comparison`() {
        assertEquals(ClientVersion(1, 12, 3), parseApkFileVersion("NEXT-Beta-android-1.12.3.apk"))
        assertNull(parseApkFileVersion("NEXT-Beta-android-latest.apk"))
        assertNull(parseApkFileVersion("../NEXT-Beta-android-2.0.0.apk"))
    }

    @Test
    fun `debug suffix is ignored in installed version comparison`() {
        assertEquals(ClientVersion(1, 0, 2), parseInstalledClientVersion("1.0.2-debug"))
    }

    @Test
    fun `highest newer APK filename is selected`() {
        val entries = parseUpdateIndex(
            """
            {
              "files": [
                {"name":"NEXT-Beta-android-1.0.2.apk","versionCode":3,"sha256":"${"a".repeat(64)}","size":120},
                {"name":"NEXT-Beta-android-1.1.0.apk","versionCode":4,"sha256":"${"b".repeat(64)}","size":130},
                {"name":"notes.txt","versionCode":99,"sha256":"${"c".repeat(64)}","size":20}
              ]
            }
            """.trimIndent(),
        )

        val update = selectNewerClientUpdate(entries, "1.0.2-debug", 3)

        assertEquals("NEXT-Beta-android-1.1.0.apk", update?.fileName)
    }

    @Test
    fun `candidate with non-increasing Android version code is rejected`() {
        val entries = parseUpdateIndex(
            """{"files":[{"name":"NEXT-Beta-android-2.0.0.apk","versionCode":3,"sha256":"${"d".repeat(64)}","size":120}]}""",
        )

        assertNull(selectNewerClientUpdate(entries, "1.0.2", 3))
    }

    @Test
    fun `malformed checksum and empty files are ignored`() {
        val entries = parseUpdateIndex(
            """{"files":[{"name":"NEXT-Beta-android-2.0.0.apk","versionCode":4,"sha256":"bad","size":0}]}""",
        )

        assertEquals(emptyList<ClientUpdateEntry>(), entries)
    }
}
