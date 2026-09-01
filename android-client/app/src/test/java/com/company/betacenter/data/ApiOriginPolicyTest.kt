package com.company.betacenter.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test
import java.net.URI

class ApiOriginPolicyTest {
    private val origin = URI("https://beta.example.com/")

    @Test
    fun `relative and exact same-origin urls are accepted`() {
        assertEquals(
            URI("https://beta.example.com/api/v1/media/image"),
            resolveSameOrigin(origin, "/api/v1/media/image"),
        )
        assertEquals(
            URI("https://beta.example.com/api/v1/downloads/file"),
            resolveSameOrigin(origin, "https://beta.example.com/api/v1/downloads/file"),
        )
    }

    @Test
    fun `host scheme and port changes are rejected`() {
        listOf(
            "https://example.test/file",
            "http://beta.example.com/file",
            "https://192.0.2.10:443/file",
            "//beta.example.com.evil.test/file",
        ).forEach { value ->
            assertThrows(IllegalArgumentException::class.java) {
                resolveSameOrigin(origin, value)
            }
        }
    }

    @Test
    fun `userinfo urls are rejected even when the host matches`() {
        assertThrows(IllegalArgumentException::class.java) {
            resolveSameOrigin(origin, "https://user@192.0.2.10:18443/file")
        }
    }
}
