package com.company.betacenter.ui.screens

import android.os.Build
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.rounded.Build
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material.icons.rounded.KeyboardArrowDown
import androidx.compose.material.icons.rounded.Lock
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.company.betacenter.data.AppDetails
import com.company.betacenter.data.BetaRepository
import com.company.betacenter.data.BugState
import com.company.betacenter.ui.AppInstallationUiState
import com.company.betacenter.ui.DownloadPhase
import com.company.betacenter.ui.DownloadUiState
import com.company.betacenter.ui.InstalledVersionMatch
import com.company.betacenter.ui.components.AuroraBackdrop
import com.company.betacenter.ui.components.ContentShape
import com.company.betacenter.ui.components.ContentSurface
import com.company.betacenter.ui.components.InlineMessage
import com.company.betacenter.ui.components.LensSurface
import com.company.betacenter.ui.components.PrivateImage
import com.company.betacenter.ui.components.PrivateImageDialog
import com.company.betacenter.ui.components.SectionHeading

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AppDetailScreen(
    repository: BetaRepository,
    app: AppDetails,
    bugCounts: Map<BugState, Int>,
    download: DownloadUiState,
    installation: AppInstallationUiState,
    message: String?,
    messageIsError: Boolean,
    onBack: () -> Unit,
    onDownload: () -> Unit,
    onCancelDownload: () -> Unit,
    onInstall: () -> Unit,
    onOpenInstalledApp: () -> Unit,
    onReportBug: () -> Unit,
    onViewBugs: () -> Unit,
    onDismissMessage: () -> Unit,
) {
    var expandedScreenshot by rememberSaveable(app.id) { mutableStateOf<String?>(null) }
    expandedScreenshot?.let { url ->
        PrivateImageDialog(
            repository = repository,
            relativeUrl = url,
            contentDescription = "${app.name} 应用截图大图",
            onDismiss = { expandedScreenshot = null },
        )
    }
    Scaffold(
        containerColor = Color.Transparent,
        topBar = {
            TopAppBar(
                title = { Text(app.name, maxLines = 1, overflow = TextOverflow.Ellipsis) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Rounded.ArrowBack, contentDescription = "返回")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = Color.Transparent),
            )
        },
    ) { scaffoldPadding ->
        Box(Modifier.fillMaxSize()) {
            AuroraBackdrop(Modifier.fillMaxWidth().height(270.dp))
            LazyColumn(
                modifier = Modifier.fillMaxSize(),
                contentPadding = PaddingValues(
                    start = 20.dp,
                    top = scaffoldPadding.calculateTopPadding() + 42.dp,
                    end = 20.dp,
                    bottom = scaffoldPadding.calculateBottomPadding() + 32.dp,
                ),
                verticalArrangement = Arrangement.spacedBy(24.dp),
            ) {
                item {
                    ReleaseHero(
                        repository = repository,
                        app = app,
                        download = download,
                        installation = installation,
                        onDownload = onDownload,
                        onCancelDownload = onCancelDownload,
                        onInstall = onInstall,
                        onOpenInstalledApp = onOpenInstalledApp,
                    )
                }
                if (message != null) {
                    item {
                        InlineMessage(
                            message,
                            isError = messageIsError,
                            actionLabel = "关闭",
                            onAction = onDismissMessage,
                        )
                    }
                }
                if (app.screenshots.isNotEmpty()) {
                    item { SectionHeading("应用截图", supporting = "左右滑动查看本次内测界面") }
                    item {
                        LazyRow(
                            contentPadding = PaddingValues(end = 18.dp),
                            horizontalArrangement = Arrangement.spacedBy(12.dp),
                        ) {
                            items(app.screenshots, key = { it.id }) { screenshot ->
                                PrivateImage(
                                    repository = repository,
                                    relativeUrl = screenshot.url,
                                    contentDescription = "${app.name} 应用截图 ${screenshot.position + 1}",
                                    modifier = Modifier
                                        .width(220.dp)
                                        .height(420.dp)
                                        .clip(RoundedCornerShape(20.dp))
                                        .clickable(onClickLabel = "全屏查看应用截图") {
                                            expandedScreenshot = screenshot.url
                                        },
                                    contentScale = ContentScale.Fit,
                                )
                            }
                        }
                    }
                }
                item {
                    SectionHeading("本次更新")
                    Spacer(Modifier.height(10.dp))
                    ContentSurface(Modifier.fillMaxWidth()) {
                        Text(
                            app.currentVersion?.releaseNotes?.ifBlank { "管理员尚未填写更新说明。" }
                                ?: "当前没有可用版本。",
                            style = MaterialTheme.typography.bodyLarge,
                        )
                    }
                }
                if (app.description.isNotBlank()) {
                    item {
                        SectionHeading("关于应用")
                        Spacer(Modifier.height(10.dp))
                        Text(
                            app.description,
                            style = MaterialTheme.typography.bodyLarge,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
                item { BugSignalCard(bugCounts, onReportBug, onViewBugs) }
            }
        }
    }
}

@Composable
private fun ReleaseHero(
    repository: BetaRepository,
    app: AppDetails,
    download: DownloadUiState,
    installation: AppInstallationUiState,
    onDownload: () -> Unit,
    onCancelDownload: () -> Unit,
    onInstall: () -> Unit,
    onOpenInstalledApp: () -> Unit,
) {
    val version = app.currentVersion
    val largeType = LocalDensity.current.fontScale >= 1.35f
    LensSurface(Modifier.fillMaxWidth()) {
        Column(verticalArrangement = Arrangement.spacedBy(20.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(16.dp), verticalAlignment = Alignment.CenterVertically) {
                PrivateImage(
                    repository,
                    app.iconUrl,
                    "${app.name} 图标",
                    Modifier.size(82.dp).clip(RoundedCornerShape(22.dp)),
                )
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(app.name, style = MaterialTheme.typography.headlineMedium, maxLines = 2)
                    Text(
                        app.shortDescription,
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Text(
                        "v${version?.versionName ?: "—"}",
                        style = MaterialTheme.typography.labelLarge,
                        fontFamily = FontFamily.Monospace,
                        color = MaterialTheme.colorScheme.primary,
                    )
                }
            }

            if (largeType) {
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Row(Modifier.fillMaxWidth()) {
                        VersionFact("大小", version?.fileSize?.let(::formatBytes) ?: "—", Modifier.weight(1f))
                        VersionFact(
                            "最低系统",
                            version?.minSdk?.let { "API $it" } ?: "未声明",
                            Modifier.weight(1f),
                        )
                    }
                    VersionFact("版本代码", version?.versionCode?.toString() ?: "—", Modifier.fillMaxWidth())
                }
            } else {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    VersionFact("大小", version?.fileSize?.let(::formatBytes) ?: "—")
                    VersionFact("最低系统", version?.minSdk?.let { "API $it" } ?: "未声明")
                    VersionFact("版本代码", version?.versionCode?.toString() ?: "—")
                }
            }

            Surface(
                color = MaterialTheme.colorScheme.secondaryContainer.copy(alpha = 0.94f),
                shape = RoundedCornerShape(14.dp),
            ) {
                Row(
                    Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 11.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(9.dp),
                ) {
                    Icon(Icons.Rounded.Lock, null, Modifier.size(18.dp), tint = MaterialTheme.colorScheme.secondary)
                    Text("平台已校验 APK 包名、版本、签名与摘要", style = MaterialTheme.typography.bodyMedium)
                }
            }

            DownloadAction(
                state = download,
                installation = installation,
                targetVersionCode = version?.versionCode,
                targetVersionName = version?.versionName,
                hasVersion = version != null,
                onDownload = onDownload,
                onCancel = onCancelDownload,
                onInstall = onInstall,
                onOpenInstalledApp = onOpenInstalledApp,
            )
        }
    }
}

@Composable
private fun VersionFact(label: String, value: String, modifier: Modifier = Modifier) {
    Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = modifier.widthIn(min = 74.dp)) {
        Text(value, style = MaterialTheme.typography.titleMedium, fontFamily = FontFamily.Monospace)
        Text(label, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
private fun DownloadAction(
    state: DownloadUiState,
    installation: AppInstallationUiState,
    targetVersionCode: Long?,
    targetVersionName: String?,
    hasVersion: Boolean,
    onDownload: () -> Unit,
    onCancel: () -> Unit,
    onInstall: () -> Unit,
    onOpenInstalledApp: () -> Unit,
) {
    val downloading = state.phase == DownloadPhase.QUEUED ||
        state.phase == DownloadPhase.PREPARING ||
        state.phase == DownloadPhase.DOWNLOADING ||
        state.phase == DownloadPhase.VERIFYING
    if (downloading) {
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
                Spacer(Modifier.width(10.dp))
                Text(
                    when (state.phase) {
                        DownloadPhase.QUEUED -> "等待网络"
                        DownloadPhase.PREPARING -> "正在获取下载许可"
                        DownloadPhase.VERIFYING -> "正在校验 APK"
                        else -> "下载中 ${state.progress}%"
                    },
                    modifier = Modifier.weight(1f),
                    style = MaterialTheme.typography.labelLarge,
                )
                IconButton(onClick = onCancel) { Icon(Icons.Rounded.Close, contentDescription = "取消下载") }
            }
            LinearProgressIndicator(
                progress = { if (state.phase == DownloadPhase.DOWNLOADING) state.progress / 100f else 0f },
                modifier = Modifier.fillMaxWidth(),
            )
        }
        return
    }

    val currentInstalled = installation.isCurrentOrNewer && installation.canOpen
    val readyToInstall = state.phase == DownloadPhase.READY
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(
            installationStatusText(installation, targetVersionCode, targetVersionName),
            style = MaterialTheme.typography.bodyMedium,
            color = if (installation.isCurrentOrNewer) {
                MaterialTheme.colorScheme.secondary
            } else {
                MaterialTheme.colorScheme.onSurfaceVariant
            },
        )

        when {
            currentInstalled -> {
                Button(
                    onClick = onOpenInstalledApp,
                    modifier = Modifier.fillMaxWidth().height(52.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.secondary),
                ) {
                    Icon(Icons.Rounded.PlayArrow, null)
                    Spacer(Modifier.width(8.dp))
                    Text("打开应用")
                }
            }
            installation.isCurrentOrNewer -> {
                Button(
                    onClick = {},
                    enabled = false,
                    modifier = Modifier.fillMaxWidth().height(52.dp),
                ) {
                    Icon(Icons.Rounded.CheckCircle, null)
                    Spacer(Modifier.width(8.dp))
                    Text("当前版本已安装")
                }
            }
            readyToInstall -> {
                Button(
                    onClick = onInstall,
                    modifier = Modifier.fillMaxWidth().height(52.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.secondary),
                ) {
                    Icon(Icons.Rounded.CheckCircle, null)
                    Spacer(Modifier.width(8.dp))
                    Text(if (installation.isInstalled) "安装更新" else "安装应用")
                }
            }
            else -> {
                Button(
                    onClick = onDownload,
                    enabled = hasVersion,
                    modifier = Modifier.fillMaxWidth().height(52.dp),
                ) {
                    Icon(Icons.Rounded.KeyboardArrowDown, null)
                    Spacer(Modifier.width(8.dp))
                    Text(
                        when {
                            !hasVersion -> "暂无可下载版本"
                            installation.isInstalled -> "下载更新"
                            state.phase == DownloadPhase.FAILED -> "重新下载"
                            else -> "下载 APK"
                        },
                    )
                }
            }
        }

        if (currentInstalled || installation.isCurrentOrNewer || readyToInstall) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                TextButton(onClick = onDownload, enabled = hasVersion) {
                    Icon(Icons.Rounded.KeyboardArrowDown, null, Modifier.size(18.dp))
                    Spacer(Modifier.width(6.dp))
                    Text("重新下载 APK")
                }
            }
        }

        if (readyToInstall && !installation.isCurrentOrNewer) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Icon(Icons.Rounded.CheckCircle, null, Modifier.size(18.dp), tint = MaterialTheme.colorScheme.secondary)
                Text("文件已下载并校验，点击安装后仍需在系统界面确认", style = MaterialTheme.typography.bodyMedium)
            }
        }
        state.error?.let {
            Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodyMedium)
        }
    }
}

private fun installationStatusText(
    installation: AppInstallationUiState,
    targetVersionCode: Long?,
    targetVersionName: String?,
): String = when (installation.match) {
    InstalledVersionMatch.NOT_INSTALLED -> "当前设备尚未安装此应用"
    InstalledVersionMatch.OUTDATED -> {
        val installed = installation.installedVersionName?.let { "v$it" }
            ?: installation.installedVersionCode?.let { "版本代码 $it" }
            ?: "较早版本"
        val target = targetVersionName?.let { "v$it" }
            ?: targetVersionCode?.let { "版本代码 $it" }
            ?: "当前版本"
        "已安装 $installed，可更新至 $target"
    }
    InstalledVersionMatch.CURRENT -> "当前版本已安装${installation.installedVersionName?.let { " · v$it" }.orEmpty()}"
    InstalledVersionMatch.NEWER -> "设备上已安装更新版本${installation.installedVersionName?.let { " · v$it" }.orEmpty()}"
    InstalledVersionMatch.INSTALLED_WITHOUT_TARGET -> "设备上已安装此应用"
}

@Composable
private fun BugSignalCard(
    counts: Map<BugState, Int>,
    onReportBug: () -> Unit,
    onViewBugs: () -> Unit,
) {
    val largeType = LocalDensity.current.fontScale >= 1.35f
    Surface(
        modifier = Modifier.fillMaxWidth(),
        color = Color(0xFF121B18),
        contentColor = Color(0xFFE7EFEA),
        shape = ContentShape,
    ) {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("反馈进展", style = MaterialTheme.typography.titleLarge)
                    Text("查看同组问题或提交新的测试证据", color = Color(0xFFB9C6C0))
                }
                Icon(Icons.Rounded.Build, null, tint = Color(0xFF77DDB8))
            }
            if (largeType) {
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Row(Modifier.fillMaxWidth()) {
                        DarkMetric("待处理", counts[BugState.PENDING] ?: 0, Color(0xFFFFC46B), Modifier.weight(1f))
                        DarkMetric("处理中", counts[BugState.IN_PROGRESS] ?: 0, Color(0xFFAEC6FF), Modifier.weight(1f))
                    }
                    Row(Modifier.fillMaxWidth()) {
                        DarkMetric("待验证", counts[BugState.VERIFYING] ?: 0, Color(0xFFC7D0FF), Modifier.weight(1f))
                        DarkMetric("已关闭", counts[BugState.CLOSED] ?: 0, Color(0xFF77DDB8), Modifier.weight(1f))
                    }
                }
            } else {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    DarkMetric("待处理", counts[BugState.PENDING] ?: 0, Color(0xFFFFC46B))
                    DarkMetric("处理中", counts[BugState.IN_PROGRESS] ?: 0, Color(0xFFAEC6FF))
                    DarkMetric("待验证", counts[BugState.VERIFYING] ?: 0, Color(0xFFC7D0FF))
                    DarkMetric("已关闭", counts[BugState.CLOSED] ?: 0, Color(0xFF77DDB8))
                }
            }
            val reportButton: @Composable (Modifier) -> Unit = { modifier ->
                Button(onClick = onReportBug, modifier = modifier) { Text("反馈 Bug") }
            }
            val viewButton: @Composable (Modifier) -> Unit = { modifier ->
                OutlinedButton(
                    onClick = onViewBugs,
                    modifier = modifier,
                    colors = ButtonDefaults.outlinedButtonColors(contentColor = Color(0xFFB6D8FF)),
                    border = BorderStroke(1.dp, Color(0xFF8FB8FF)),
                ) { Text("查看反馈") }
            }
            if (largeType) {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    reportButton(Modifier.fillMaxWidth())
                    viewButton(Modifier.fillMaxWidth())
                }
            } else {
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    reportButton(Modifier.weight(1f))
                    viewButton(Modifier.weight(1f))
                }
            }
        }
    }
}

@Composable
private fun DarkMetric(label: String, value: Int, color: Color, modifier: Modifier = Modifier) {
    Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = modifier) {
        Text(value.toString(), color = color, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
        Text(label, color = Color(0xFFB9C6C0), style = MaterialTheme.typography.labelMedium)
    }
}

private fun formatBytes(bytes: Long): String = when {
    bytes >= 1024L * 1024L * 1024L -> "%.1f GB".format(bytes / (1024.0 * 1024.0 * 1024.0))
    bytes >= 1024L * 1024L -> "%.1f MB".format(bytes / (1024.0 * 1024.0))
    bytes >= 1024L -> "%.0f KB".format(bytes / 1024.0)
    else -> "$bytes B"
}
