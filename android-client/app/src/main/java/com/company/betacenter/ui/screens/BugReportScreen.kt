package com.company.betacenter.ui.screens

import android.net.Uri
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.Check
import androidx.compose.material.icons.rounded.Delete
import androidx.compose.material.icons.rounded.Lock
import androidx.compose.material.icons.rounded.Phone
import androidx.compose.material3.BottomAppBar
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.unit.dp
import androidx.core.net.toUri
import com.company.betacenter.BuildConfig
import com.company.betacenter.data.AppDetails
import com.company.betacenter.data.BetaRepository
import com.company.betacenter.data.BugDraft
import com.company.betacenter.data.BugDraftStore
import com.company.betacenter.ui.components.ContentSurface
import com.company.betacenter.ui.components.InlineMessage
import com.company.betacenter.ui.components.LensSurface
import com.company.betacenter.ui.components.LocalUriImage
import com.company.betacenter.ui.components.PrivateImage
import com.company.betacenter.ui.components.SectionHeading
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BugReportScreen(
    repository: BetaRepository,
    draftStore: BugDraftStore,
    userId: String,
    app: AppDetails,
    submitting: Boolean,
    message: String?,
    messageIsError: Boolean,
    onBack: () -> Unit,
    onSubmit: (BugDraft) -> Unit,
    onDismissMessage: () -> Unit,
) {
    val version = app.currentVersion ?: return
    var title by rememberSaveable(app.id, version.id) { mutableStateOf("") }
    var description by rememberSaveable(app.id, version.id) { mutableStateOf("") }
    var steps by rememberSaveable(app.id, version.id) { mutableStateOf("") }
    var visibility by rememberSaveable(app.id, version.id) { mutableStateOf("group") }
    var screenshotStrings by rememberSaveable(app.id, version.id) { mutableStateOf(emptyList<String>()) }
    var evidenceBusy by remember { mutableStateOf(false) }
    var localError by remember { mutableStateOf<String?>(null) }
    var restored by remember(app.id, version.id) { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    LaunchedEffect(userId, app.id, version.id) {
        draftStore.load(userId, app.id, version.id)?.let { draft ->
            title = draft.title
            description = draft.description
            steps = draft.reproductionSteps
            visibility = draft.visibility
            screenshotStrings = draft.screenshots.map(Uri::toString)
        }
        restored = true
    }

    LaunchedEffect(restored, title, description, steps, visibility, screenshotStrings) {
        if (!restored) return@LaunchedEffect
        delay(500)
        draftStore.save(
            userId,
            BugDraft(
                appId = app.id,
                versionId = version.id,
                title = title,
                description = description,
                reproductionSteps = steps,
                visibility = visibility,
                screenshots = screenshotStrings.map(String::toUri),
            ),
        )
    }

    val picker = rememberLauncherForActivityResult(ActivityResultContracts.PickMultipleVisualMedia(5)) { uris ->
        if (uris.isEmpty()) return@rememberLauncherForActivityResult
        scope.launch {
            evidenceBusy = true
            localError = null
            val remaining = (5 - screenshotStrings.size).coerceAtLeast(0)
            val imported = mutableListOf<String>()
            try {
                uris.take(remaining).forEach { selected ->
                    imported += repository.importBugScreenshot(selected).toString()
                }
                screenshotStrings = (screenshotStrings + imported).distinct().take(5)
            } catch (exception: Exception) {
                repository.deleteDraftScreenshots(imported.map(String::toUri))
                localError = exception.message ?: "无法处理所选截图"
            } finally {
                evidenceBusy = false
            }
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("反馈 Bug") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Rounded.ArrowBack, contentDescription = "返回")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.background),
            )
        },
        bottomBar = {
            BottomAppBar(
                modifier = Modifier.imePadding(),
                containerColor = MaterialTheme.colorScheme.surface.copy(alpha = 0.98f),
                contentPadding = PaddingValues(horizontal = 18.dp, vertical = 10.dp),
            ) {
                Column(Modifier.weight(1f)) {
                    Text("草稿自动保存", style = MaterialTheme.typography.labelLarge)
                    Text(
                        if (screenshotStrings.isEmpty()) "可不上传截图" else "已保留 ${screenshotStrings.size} 张证据",
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                Button(
                    onClick = {
                        onSubmit(
                            BugDraft(
                                app.id,
                                version.id,
                                title,
                                description,
                                steps,
                                visibility,
                                screenshotStrings.map(String::toUri),
                            ),
                        )
                    },
                    enabled = !submitting && !evidenceBusy,
                    modifier = Modifier.height(50.dp),
                ) {
                    if (submitting) {
                        CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp, color = Color.White)
                    } else {
                        Icon(Icons.Rounded.Check, null)
                    }
                    Spacer(Modifier.width(8.dp))
                    Text(if (submitting) "提交中" else "提交反馈")
                }
            }
        },
    ) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(
                start = 20.dp,
                top = padding.calculateTopPadding() + 12.dp,
                end = 20.dp,
                bottom = padding.calculateBottomPadding() + 24.dp,
            ),
            verticalArrangement = Arrangement.spacedBy(22.dp),
        ) {
            item {
                LensSurface(Modifier.fillMaxWidth()) {
                    Row(horizontalArrangement = Arrangement.spacedBy(14.dp), verticalAlignment = Alignment.CenterVertically) {
                        PrivateImage(
                            repository,
                            app.iconUrl,
                            "${app.name} 图标",
                            Modifier.size(62.dp).clip(RoundedCornerShape(17.dp)),
                        )
                        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                            Text(app.name, style = MaterialTheme.typography.titleLarge)
                            Text("绑定版本 v${version.versionName}", color = MaterialTheme.colorScheme.primary)
                            Text(
                                app.packageName,
                                style = MaterialTheme.typography.labelMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                }
            }
            if (message != null || localError != null) {
                item {
                    InlineMessage(
                        message = localError ?: message.orEmpty(),
                        isError = localError != null || messageIsError,
                        actionLabel = "关闭",
                        onAction = {
                            localError = null
                            onDismissMessage()
                        },
                    )
                }
            }
            item {
                SectionHeading("问题描述", supporting = "请写清现象、预期结果和稳定复现路径")
                Spacer(Modifier.height(10.dp))
                ContentSurface(Modifier.fillMaxWidth()) {
                    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
                        OutlinedTextField(
                            value = title,
                            onValueChange = { if (it.length <= 120) title = it },
                            modifier = Modifier.fillMaxWidth(),
                            label = { Text("Bug 标题") },
                            supportingText = { Text("${title.length}/120") },
                            singleLine = true,
                            keyboardOptions = KeyboardOptions(
                                capitalization = KeyboardCapitalization.Sentences,
                                imeAction = ImeAction.Next,
                            ),
                        )
                        OutlinedTextField(
                            value = description,
                            onValueChange = { if (it.length <= 10_000) description = it },
                            modifier = Modifier.fillMaxWidth(),
                            label = { Text("实际发生了什么") },
                            supportingText = { Text("${description.length}/10000") },
                            minLines = 4,
                            maxLines = 9,
                        )
                        OutlinedTextField(
                            value = steps,
                            onValueChange = { if (it.length <= 5000) steps = it },
                            modifier = Modifier.fillMaxWidth(),
                            label = { Text("复现步骤（可选）") },
                            supportingText = { Text("${steps.length}/5000") },
                            minLines = 3,
                            maxLines = 7,
                        )
                    }
                }
            }
            item {
                SectionHeading("截图与环境", supporting = "截图只用于定位本次内测问题")
                Spacer(Modifier.height(10.dp))
                ContentSurface(Modifier.fillMaxWidth()) {
                    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
                        if (screenshotStrings.isNotEmpty()) {
                            LazyRow(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                                itemsIndexed(screenshotStrings, key = { _, value -> value }) { index, value ->
                                    Box {
                                        LocalUriImage(
                                            value.toUri(),
                                            "反馈截图 ${index + 1}",
                                            Modifier.size(width = 116.dp, height = 172.dp).clip(RoundedCornerShape(14.dp)),
                                        )
                                        IconButton(
                                            onClick = {
                                                repository.deleteDraftScreenshots(listOf(value.toUri()))
                                                screenshotStrings = screenshotStrings.filterNot { it == value }
                                            },
                                            modifier = Modifier.align(Alignment.TopEnd).size(48.dp),
                                        ) {
                                            Icon(
                                                Icons.Rounded.Delete,
                                                contentDescription = "删除截图 ${index + 1}",
                                                tint = MaterialTheme.colorScheme.error,
                                            )
                                        }
                                    }
                                }
                            }
                        }
                        OutlinedButton(
                            onClick = {
                                picker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
                            },
                            enabled = screenshotStrings.size < 5 && !evidenceBusy,
                            modifier = Modifier.fillMaxWidth().height(50.dp),
                        ) {
                            if (evidenceBusy) CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
                            else Icon(Icons.Rounded.Add, null)
                            Spacer(Modifier.width(8.dp))
                            Text(if (evidenceBusy) "正在安全处理截图" else "从相册选择截图（${screenshotStrings.size}/5）")
                        }
                        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.Top) {
                            Icon(Icons.Rounded.Lock, null, tint = MaterialTheme.colorScheme.primary)
                            Text(
                                "上传前会移除图片元数据并压缩。Bug 截图仅你和管理员可查看。",
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Rounded.Phone, null)
                            Text(
                                "${Build.MANUFACTURER} ${Build.MODEL} · Android ${Build.VERSION.RELEASE} · 客户端 ${BuildConfig.VERSION_NAME}",
                                style = MaterialTheme.typography.bodyMedium,
                            )
                        }
                        Text("谁可以看到基本信息", style = MaterialTheme.typography.titleMedium)
                        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                            FilterChip(
                                selected = visibility == "group",
                                onClick = { visibility = "group" },
                                label = { Text("同组测试用户") },
                            )
                            FilterChip(
                                selected = visibility == "private",
                                onClick = { visibility = "private" },
                                label = { Text("仅自己") },
                            )
                        }
                    }
                }
            }
        }
    }
}
