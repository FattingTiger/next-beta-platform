package com.company.qa.playground

import java.util.Locale

data class QaResult(
    val code: String,
    val createdAtMillis: Long,
    val recordedPasses: Int,
    val completedChecks: Int,
    val verdict: String,
)

object QaResultGenerator {
    fun generate(recordedPasses: Int, createdAtMillis: Long): QaResult {
        require(recordedPasses >= 0) { "recordedPasses must not be negative" }
        require(createdAtMillis >= 0L) { "createdAtMillis must not be negative" }

        val minuteBucket = (createdAtMillis / 60_000L) % 100_000L
        val visibleCount = recordedPasses.coerceAtMost(99)
        val code = String.format(Locale.ROOT, "QA-%05d-%02d", minuteBucket, visibleCount)
        val hasInteractionRecord = recordedPasses > 0

        return QaResult(
            code = code,
            createdAtMillis = createdAtMillis,
            recordedPasses = recordedPasses,
            completedChecks = if (hasInteractionRecord) 3 else 2,
            verdict = if (hasInteractionRecord) "全项通过" else "基础链路通过",
        )
    }
}

