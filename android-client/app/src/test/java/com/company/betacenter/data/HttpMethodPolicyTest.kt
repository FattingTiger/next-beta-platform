package com.company.betacenter.data

import org.junit.Assert.assertFalse
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class HttpMethodPolicyTest {
    @Test
    fun `patch bypasses HttpURLConnection method restriction`() {
        assertTrue(usesExtendedHttpTransport("PATCH"))
        assertFalse(usesExtendedHttpTransport("GET"))
        assertFalse(usesExtendedHttpTransport("POST"))
        assertFalse(usesExtendedHttpTransport("PUT"))
        assertFalse(usesExtendedHttpTransport("DELETE"))
    }

    @Test
    fun `bug edit payload includes every editable text field`() {
        val json = bugTextUpdateJson(BugTextUpdate("新标题", "新描述", "新步骤"))

        assertEquals(setOf("title", "description", "reproduction_steps"), json.keys().asSequence().toSet())
        assertEquals("新标题", json.getString("title"))
        assertEquals("新描述", json.getString("description"))
        assertEquals("新步骤", json.getString("reproduction_steps"))
    }
}
