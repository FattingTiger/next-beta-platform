package com.company.qa.playground

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class QaResultGeneratorTest {
    @Test
    fun `recorded interaction produces full pass result`() {
        val result = QaResultGenerator.generate(recordedPasses = 3, createdAtMillis = 6_000_000L)

        assertEquals("QA-00100-03", result.code)
        assertEquals(3, result.recordedPasses)
        assertEquals(3, result.completedChecks)
        assertEquals("全项通过", result.verdict)
    }

    @Test
    fun `zero interactions still validates basic distribution chain`() {
        val result = QaResultGenerator.generate(recordedPasses = 0, createdAtMillis = 0L)

        assertEquals("QA-00000-00", result.code)
        assertEquals(2, result.completedChecks)
        assertEquals("基础链路通过", result.verdict)
    }

    @Test
    fun `negative interaction count is rejected`() {
        assertThrows(IllegalArgumentException::class.java) {
            QaResultGenerator.generate(recordedPasses = -1, createdAtMillis = 0L)
        }
    }
}

