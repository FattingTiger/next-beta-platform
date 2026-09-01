package com.company.betacenter.ui

import com.company.betacenter.data.ApiException
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test
import java.io.IOException

class FailureMessageTest {
    @Test
    fun `server business message remains actionable`() {
        val exception = ApiException(409, "version_conflict", "版本已变化，请刷新后重试")

        assertEquals("版本已变化，请刷新后重试", userFacingFailureMessage(exception))
    }

    @Test
    fun `network failure does not expose endpoint details`() {
        val result = userFacingFailureMessage(
            IOException("failed to connect to /192.0.2.10:18443"),
        )

        assertEquals("网络连接失败，请检查网络后重试", result)
        assertFalse(result.contains("192.0.2.10"))
    }

    @Test
    fun `unexpected implementation failure stays generic`() {
        assertEquals(
            "操作未完成，请稍后重试",
            userFacingFailureMessage(IllegalStateException("internal invariant and object id")),
        )
    }
}
