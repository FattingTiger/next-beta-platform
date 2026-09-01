package com.company.betacenter.ui

import com.company.betacenter.data.BugReport
import com.company.betacenter.data.BugState
import com.company.betacenter.data.BugTextUpdate
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

class BugEditPolicyTest {
    @Test
    fun `only the reporter can edit a pending bug`() {
        assertTrue(canEditBugText("user-1", "user-1", BugState.PENDING))
        assertFalse(canEditBugText("user-2", "user-1", BugState.PENDING))
        assertFalse(canEditBugText(null, "user-1", BugState.PENDING))
        assertFalse(canEditBugText("user-1", "user-1", BugState.IN_PROGRESS))
        assertFalse(canEditBugText("user-1", "user-1", BugState.VERIFYING))
        assertFalse(canEditBugText("user-1", "user-1", BugState.CLOSED))
    }

    @Test
    fun `edit input is trimmed before validation and submission`() {
        assertEquals(
            BugTextUpdate("标题", "问题描述", "第一步\n第二步"),
            normalizedBugTextUpdate("  标题  ", "\n问题描述\t", "  第一步\n第二步  "),
        )
    }

    @Test
    fun `valid edit accepts boundary lengths`() {
        assertNull(validateBugTextUpdate(BugTextUpdate("标".repeat(2), "描".repeat(2), "")))
        assertNull(
            validateBugTextUpdate(
                BugTextUpdate("标".repeat(120), "描".repeat(10_000), "步".repeat(5000)),
            ),
        )
    }

    @Test
    fun `invalid edit reports the first actionable constraint`() {
        assertEquals(
            "Bug 标题需要 2–120 个字符",
            validateBugTextUpdate(BugTextUpdate("短", "有效描述", "")),
        )
        assertEquals(
            "问题描述需要 2–10000 个字符",
            validateBugTextUpdate(BugTextUpdate("有效标题", "短", "")),
        )
        assertEquals(
            "复现步骤不能超过 5000 个字符",
            validateBugTextUpdate(BugTextUpdate("有效标题", "有效描述", "步".repeat(5001))),
        )
    }

    @Test
    fun `change detection avoids a no-op patch`() {
        val original = bug()

        assertFalse(hasBugTextChanges(original, BugTextUpdate("原始标题", "原始描述", "原始步骤")))
        assertTrue(hasBugTextChanges(original, BugTextUpdate("更新标题", "原始描述", "原始步骤")))
        assertTrue(hasBugTextChanges(original, BugTextUpdate("原始标题", "更新描述", "原始步骤")))
        assertTrue(hasBugTextChanges(original, BugTextUpdate("原始标题", "原始描述", "更新步骤")))
    }

    @Test
    fun `matching pending response is accepted`() {
        val original = bug()
        val update = BugTextUpdate("更新标题", "更新描述", "更新步骤")
        val updated = original.copy(
            title = update.title,
            description = update.description,
            reproductionSteps = update.reproductionSteps,
        )

        validateBugTextUpdateResponse(original, updated, "user-1", update)
    }

    @Test
    fun `response from another bug or account is rejected`() {
        val original = bug()
        val update = BugTextUpdate("更新标题", "更新描述", "更新步骤")

        assertThrows(IllegalStateException::class.java) {
            validateBugTextUpdateResponse(
                original,
                original.copy(id = "bug-2", title = update.title, description = update.description),
                "user-1",
                update,
            )
        }
        assertThrows(IllegalStateException::class.java) {
            validateBugTextUpdateResponse(
                original,
                original.copy(title = update.title, description = update.description, reporterId = "user-2"),
                "user-1",
                update,
            )
        }
    }

    @Test
    fun `stale status or mismatched returned text is rejected`() {
        val original = bug()
        val update = BugTextUpdate("更新标题", "更新描述", "更新步骤")

        assertThrows(IllegalStateException::class.java) {
            validateBugTextUpdateResponse(
                original,
                original.copy(
                    title = update.title,
                    description = update.description,
                    reproductionSteps = update.reproductionSteps,
                    status = BugState.IN_PROGRESS,
                ),
                "user-1",
                update,
            )
        }
        assertThrows(IllegalStateException::class.java) {
            validateBugTextUpdateResponse(
                original,
                original.copy(title = "服务端旧标题", description = update.description),
                "user-1",
                update,
            )
        }
    }

    private fun bug() = BugReport(
        id = "bug-1",
        reference = "BT-ABC12345",
        appId = "app-1",
        appName = "QA 试验场",
        versionId = "version-1",
        versionName = "1.0.0",
        reporterId = "user-1",
        reporterName = "测试员工",
        title = "原始标题",
        description = "原始描述",
        reproductionSteps = "原始步骤",
        deviceModel = "Android SDK",
        androidVersion = "16",
        clientVersion = "1.0.0-debug",
        status = BugState.PENDING,
        visibility = "group",
        resolution = null,
        resolutionNote = "",
        fixVersionId = null,
        attachments = emptyList(),
        comments = emptyList(),
        transitions = emptyList(),
        createdAt = "2026-08-29T00:00:00Z",
        updatedAt = "2026-08-29T00:00:00Z",
    )
}
