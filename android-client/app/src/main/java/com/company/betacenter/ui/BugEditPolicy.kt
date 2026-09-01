package com.company.betacenter.ui

import com.company.betacenter.data.BugReport
import com.company.betacenter.data.BugState
import com.company.betacenter.data.BugTextUpdate

internal fun canEditBugText(
    reporterId: String?,
    currentUserId: String,
    status: BugState,
): Boolean = reporterId == currentUserId && status == BugState.PENDING

internal fun normalizedBugTextUpdate(
    title: String,
    description: String,
    reproductionSteps: String,
): BugTextUpdate = BugTextUpdate(
    title = title.trim(),
    description = description.trim(),
    reproductionSteps = reproductionSteps.trim(),
)

internal fun validateBugTextUpdate(update: BugTextUpdate): String? = when {
    update.title.length !in 2..120 -> "Bug 标题需要 2–120 个字符"
    update.description.length !in 2..10_000 -> "问题描述需要 2–10000 个字符"
    update.reproductionSteps.length > 5000 -> "复现步骤不能超过 5000 个字符"
    else -> null
}

internal fun hasBugTextChanges(original: BugReport, update: BugTextUpdate): Boolean =
    original.title != update.title ||
        original.description.orEmpty() != update.description ||
        original.reproductionSteps.orEmpty() != update.reproductionSteps

internal fun validateBugTextUpdateResponse(
    original: BugReport,
    updated: BugReport,
    currentUserId: String,
    expected: BugTextUpdate,
) {
    check(
        updated.id == original.id &&
            updated.appId == original.appId &&
            updated.versionId == original.versionId,
    ) { "服务器返回的 Bug 与当前操作不匹配" }
    check(updated.reporterId == currentUserId) { "Bug 编辑账户不匹配" }
    check(updated.status == BugState.PENDING) { "Bug 状态已变化，请刷新后重试" }
    check(
        updated.title == expected.title &&
            updated.description.orEmpty() == expected.description &&
            updated.reproductionSteps.orEmpty() == expected.reproductionSteps,
    ) { "服务器返回的 Bug 文本与提交内容不匹配" }
}
