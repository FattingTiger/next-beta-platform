package com.company.betacenter.data

import android.net.Uri

data class UserProfile(
    val id: String,
    val displayName: String,
    val phone: String,
    val role: String,
    val mustChangePassword: Boolean,
    val groupIds: List<String>,
)

data class AuthSession(
    val accessToken: String,
    val refreshToken: String,
    val expiresAtEpochMillis: Long,
    val user: UserProfile,
)

data class AppVersion(
    val id: String,
    val versionName: String,
    val versionCode: Long,
    val minSdk: Int?,
    val targetSdk: Int?,
    val fileSize: Long,
    val sha256: String,
    val signingCertSha256: String,
    val releaseNotes: String,
    val publishedAt: String?,
    val downloadEnabled: Boolean,
)

data class AppCard(
    val id: String,
    val name: String,
    val packageName: String,
    val shortDescription: String,
    val iconUrl: String?,
    val currentVersion: AppVersion?,
    val updatedAt: String,
)

data class AppScreenshot(
    val id: String,
    val position: Int,
    val contentType: String,
    val url: String,
)

data class AppDetails(
    val id: String,
    val name: String,
    val packageName: String,
    val shortDescription: String,
    val description: String,
    val iconUrl: String?,
    val currentVersion: AppVersion?,
    val screenshots: List<AppScreenshot>,
    val updatedAt: String,
)

enum class BugState(val wireValue: String) {
    PENDING("pending"),
    IN_PROGRESS("in_progress"),
    VERIFYING("verifying"),
    CLOSED("closed"),
    UNKNOWN("unknown");

    companion object {
        fun fromWire(value: String): BugState = entries.firstOrNull { it.wireValue == value } ?: UNKNOWN
    }
}

data class BugAttachment(
    val id: String,
    val contentType: String,
    val fileSize: Long,
    val url: String,
)

data class BugComment(
    val id: String,
    val authorName: String,
    val content: String,
    val createdAt: String,
)

data class BugTransition(
    val id: String,
    val actorName: String,
    val fromStatus: BugState?,
    val toStatus: BugState,
    val note: String,
    val createdAt: String,
)

data class BugReport(
    val id: String,
    val reference: String,
    val appId: String,
    val appName: String,
    val versionId: String,
    val versionName: String,
    val reporterId: String?,
    val reporterName: String?,
    val title: String,
    val description: String?,
    val reproductionSteps: String?,
    val deviceModel: String?,
    val androidVersion: String?,
    val clientVersion: String?,
    val status: BugState,
    val visibility: String,
    val resolution: String?,
    val resolutionNote: String,
    val fixVersionId: String?,
    val attachments: List<BugAttachment>,
    val comments: List<BugComment>,
    val transitions: List<BugTransition>,
    val createdAt: String,
    val updatedAt: String,
)

data class BugPage(
    val items: List<BugReport>,
    val total: Int,
    val page: Int,
    val pageSize: Int,
)

data class BugTextUpdate(
    val title: String,
    val description: String,
    val reproductionSteps: String,
)

data class BugDraft(
    val appId: String,
    val versionId: String,
    val title: String,
    val description: String,
    val reproductionSteps: String,
    val visibility: String = "group",
    val screenshots: List<Uri> = emptyList(),
)

data class DownloadTicket(
    val downloadId: String,
    val clientRequestId: String,
    val url: String,
    val fileSize: Long,
    val sha256: String,
    val filename: String,
)

class ApiException(
    val statusCode: Int,
    val errorCode: String,
    override val message: String,
    val requestId: String? = null,
) : Exception(message)
