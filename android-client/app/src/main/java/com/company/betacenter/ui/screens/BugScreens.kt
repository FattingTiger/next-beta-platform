package com.company.betacenter.ui.screens

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
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.automirrored.rounded.ArrowForward
import androidx.compose.material.icons.rounded.Build
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Edit
import androidx.compose.material.icons.rounded.MailOutline
import androidx.compose.material.icons.rounded.Refresh
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
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.company.betacenter.data.BetaRepository
import com.company.betacenter.data.BugReport
import com.company.betacenter.data.BugState
import com.company.betacenter.ui.canEditBugText
import com.company.betacenter.ui.components.BugStatusPill
import com.company.betacenter.ui.components.ContentSurface
import com.company.betacenter.ui.components.InlineMessage
import com.company.betacenter.ui.components.LensSurface
import com.company.betacenter.ui.components.PrivateImage
import com.company.betacenter.ui.components.PrivateImageDialog
import com.company.betacenter.ui.components.SectionHeading
import com.company.betacenter.ui.hasBugTextChanges
import com.company.betacenter.ui.normalizedBugTextUpdate
import com.company.betacenter.ui.validateBugTextUpdate

@Composable
fun BugListScreen(
    bugs: List<BugReport>,
    mine: Boolean,
    appScopeName: String?,
    total: Int,
    loading: Boolean,
    loadingMore: Boolean,
    message: String?,
    messageIsError: Boolean,
    onModeChange: (Boolean) -> Unit,
    onOpenBug: (String) -> Unit,
    onRefresh: () -> Unit,
    onLoadMore: () -> Unit,
    onDismissMessage: () -> Unit,
) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 20.dp, top = 34.dp, end = 20.dp, bottom = 28.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp),
    ) {
        item {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("测试反馈", style = MaterialTheme.typography.headlineLarge)
                    Text("Bug 的处理状态会持续保留在这里", color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                IconButton(onClick = onRefresh, enabled = !loading) {
                    Icon(Icons.Rounded.Refresh, contentDescription = "刷新反馈")
                }
            }
        }
        item {
            LensSurface(Modifier.fillMaxWidth()) {
                Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        Icon(Icons.Rounded.Build, null, tint = MaterialTheme.colorScheme.primary)
                        Column {
                            Text(
                                appScopeName?.let { "$it · $total 条反馈" } ?: "$total 条可见反馈",
                                style = MaterialTheme.typography.titleLarge,
                            )
                            Text(
                                when {
                                    appScopeName != null && mine -> "仅显示你为该应用提交的问题"
                                    appScopeName != null -> "包含你提交的问题与该应用的同组公开反馈"
                                    mine -> "只显示由你提交的问题"
                                    else -> "包含你提交的问题与同测试组公开的基本信息"
                                },
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        FilterChip(selected = mine, onClick = { onModeChange(true) }, label = { Text("我的反馈") })
                        FilterChip(selected = !mine, onClick = { onModeChange(false) }, label = { Text("全部可见") })
                    }
                }
            }
        }
        if (message != null) {
            item {
                InlineMessage(message, isError = messageIsError, actionLabel = "关闭", onAction = onDismissMessage)
            }
        }
        if (loading && bugs.isEmpty()) {
            item {
                Box(Modifier.fillMaxWidth().height(180.dp), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator()
                }
            }
        } else if (bugs.isEmpty()) {
            item {
                Column(
                    Modifier.fillMaxWidth().padding(vertical = 52.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Text(if (mine) "你还没有提交反馈" else "当前没有可见反馈", style = MaterialTheme.typography.titleLarge)
                    Text("从应用详情页进入即可反馈 Bug", color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        } else {
            item {
                SectionHeading(
                    appScopeName?.let { "$it 的反馈" } ?: if (mine) "我的反馈" else "全部可见",
                )
            }
            items(bugs, key = BugReport::id) { bug ->
                BugListRow(bug, onOpenBug)
            }
            if (bugs.size < total) {
                item {
                    OutlinedButton(
                        onClick = onLoadMore,
                        enabled = !loadingMore,
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        if (loadingMore) {
                            CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
                            Spacer(Modifier.width(8.dp))
                        }
                        Text(if (loadingMore) "加载中" else "加载更多（${bugs.size}/$total）")
                    }
                }
            }
        }
    }
}

@Composable
private fun BugListRow(bug: BugReport, onOpenBug: (String) -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClickLabel = "查看 ${bug.reference}") { onOpenBug(bug.id) }
            .padding(vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(bug.reference, style = MaterialTheme.typography.labelLarge, fontFamily = FontFamily.Monospace)
            Spacer(Modifier.weight(1f))
            BugStatusPill(bug.status)
        }
        Text(bug.title, style = MaterialTheme.typography.titleMedium, maxLines = 2, overflow = TextOverflow.Ellipsis)
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                "${bug.appName} · v${bug.versionName}",
                modifier = Modifier.weight(1f),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Icon(Icons.AutoMirrored.Rounded.ArrowForward, null, Modifier.size(19.dp))
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BugDetailScreen(
    repository: BetaRepository,
    currentUserId: String,
    bug: BugReport,
    loading: Boolean,
    editBusy: Boolean,
    editSubmitSequence: Int,
    commentBusy: Boolean,
    commentSubmitSequence: Int,
    message: String?,
    messageIsError: Boolean,
    onBack: () -> Unit,
    onEdit: (title: String, description: String, reproductionSteps: String) -> Unit,
    onComment: (String) -> Unit,
    onVerify: (Boolean, String) -> Unit,
    onDismissMessage: () -> Unit,
) {
    var comment by rememberSaveable(bug.id) { mutableStateOf("") }
    var consumedCommentSequence by rememberSaveable(bug.id) { mutableIntStateOf(commentSubmitSequence) }
    var verificationNote by rememberSaveable(bug.id) { mutableStateOf("") }
    var expandedAttachment by rememberSaveable(bug.id) { mutableStateOf<String?>(null) }
    val isReporter = bug.reporterId == currentUserId
    val canEdit = canEditBugText(bug.reporterId, currentUserId, bug.status)
    var editing by rememberSaveable(bug.id) { mutableStateOf(false) }
    var editTitle by rememberSaveable(bug.id) { mutableStateOf(bug.title) }
    var editDescription by rememberSaveable(bug.id) { mutableStateOf(bug.description.orEmpty()) }
    var editSteps by rememberSaveable(bug.id) { mutableStateOf(bug.reproductionSteps.orEmpty()) }
    var consumedEditSequence by rememberSaveable(bug.id) { mutableIntStateOf(editSubmitSequence) }
    val editUpdate = normalizedBugTextUpdate(editTitle, editDescription, editSteps)
    val editValidation = validateBugTextUpdate(editUpdate)
    val editChanged = hasBugTextChanges(bug, editUpdate)

    fun startEditing() {
        editTitle = bug.title
        editDescription = bug.description.orEmpty()
        editSteps = bug.reproductionSteps.orEmpty()
        editing = true
        onDismissMessage()
    }

    fun cancelEditing() {
        editTitle = bug.title
        editDescription = bug.description.orEmpty()
        editSteps = bug.reproductionSteps.orEmpty()
        editing = false
    }

    expandedAttachment?.let { url ->
        PrivateImageDialog(
            repository = repository,
            relativeUrl = url,
            contentDescription = "${bug.reference} 截图证据大图",
            onDismiss = { expandedAttachment = null },
        )
    }

    LaunchedEffect(commentSubmitSequence) {
        if (commentSubmitSequence > consumedCommentSequence) {
            comment = ""
            consumedCommentSequence = commentSubmitSequence
        }
    }

    LaunchedEffect(editSubmitSequence) {
        if (editSubmitSequence > consumedEditSequence) {
            editTitle = bug.title
            editDescription = bug.description.orEmpty()
            editSteps = bug.reproductionSteps.orEmpty()
            editing = false
            consumedEditSequence = editSubmitSequence
        }
    }

    LaunchedEffect(canEdit) {
        if (!canEdit) editing = false
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(bug.reference, fontFamily = FontFamily.Monospace) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Rounded.ArrowBack, contentDescription = "返回")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.background),
            )
        },
    ) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(
                start = 20.dp,
                top = padding.calculateTopPadding() + 12.dp,
                end = 20.dp,
                bottom = padding.calculateBottomPadding() + 30.dp,
            ),
            verticalArrangement = Arrangement.spacedBy(20.dp),
        ) {
            item {
                LensSurface(Modifier.fillMaxWidth()) {
                    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            BugStatusPill(bug.status)
                            Spacer(Modifier.weight(1f))
                            Text("v${bug.versionName}", fontFamily = FontFamily.Monospace)
                        }
                        Text(bug.title, style = MaterialTheme.typography.headlineMedium)
                        Text("${bug.appName} · ${bug.reference}", color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
            if (message != null) {
                item {
                    InlineMessage(message, isError = messageIsError, actionLabel = "关闭", onAction = onDismissMessage)
                }
            }
            if (editing && canEdit) {
                item {
                    SectionHeading("问题信息")
                    Spacer(Modifier.height(10.dp))
                    ContentSurface(Modifier.fillMaxWidth()) {
                        Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
                            Row(
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(10.dp),
                            ) {
                                Icon(Icons.Rounded.Edit, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                                Column {
                                    Text("编辑反馈内容", style = MaterialTheme.typography.titleMedium)
                                    Text(
                                        "仅待处理阶段可修改，保存后会同步到反馈列表。",
                                        style = MaterialTheme.typography.bodyMedium,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    )
                                }
                            }
                            OutlinedTextField(
                                value = editTitle,
                                onValueChange = { if (it.length <= 120) editTitle = it },
                                modifier = Modifier.fillMaxWidth(),
                                label = { Text("Bug 标题") },
                                supportingText = { Text("${editTitle.length}/120") },
                                singleLine = true,
                            )
                            OutlinedTextField(
                                value = editDescription,
                                onValueChange = { if (it.length <= 10_000) editDescription = it },
                                modifier = Modifier.fillMaxWidth(),
                                label = { Text("问题描述") },
                                supportingText = { Text("${editDescription.length}/10000") },
                                minLines = 4,
                                maxLines = 8,
                            )
                            OutlinedTextField(
                                value = editSteps,
                                onValueChange = { if (it.length <= 5000) editSteps = it },
                                modifier = Modifier.fillMaxWidth(),
                                label = { Text("复现步骤（可选）") },
                                supportingText = { Text("${editSteps.length}/5000") },
                                minLines = 3,
                                maxLines = 7,
                            )
                            if (editValidation != null) {
                                InlineMessage(editValidation, isError = true)
                            }
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.spacedBy(10.dp),
                            ) {
                                OutlinedButton(
                                    onClick = ::cancelEditing,
                                    enabled = !editBusy,
                                    modifier = Modifier.weight(1f).heightIn(min = 48.dp),
                                ) {
                                    Text("取消")
                                }
                                Button(
                                    onClick = {
                                        onEdit(editUpdate.title, editUpdate.description, editUpdate.reproductionSteps)
                                    },
                                    enabled = editValidation == null && editChanged && !editBusy,
                                    modifier = Modifier.weight(1f).heightIn(min = 48.dp),
                                ) {
                                    if (editBusy) {
                                        CircularProgressIndicator(
                                            Modifier.size(18.dp),
                                            color = MaterialTheme.colorScheme.onPrimary,
                                            strokeWidth = 2.dp,
                                        )
                                        Spacer(Modifier.width(8.dp))
                                    }
                                    Text(if (editBusy) "保存中" else "保存修改")
                                }
                            }
                        }
                    }
                }
            } else if (bug.description != null || canEdit) {
                item {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        SectionHeading("问题信息", modifier = Modifier.weight(1f))
                        if (canEdit) {
                            OutlinedButton(
                                onClick = ::startEditing,
                                enabled = !loading && !commentBusy && !editBusy,
                                modifier = Modifier.heightIn(min = 48.dp),
                            ) {
                                Icon(Icons.Rounded.Edit, contentDescription = null, modifier = Modifier.size(18.dp))
                                Spacer(Modifier.width(8.dp))
                                Text("编辑")
                            }
                        }
                    }
                    Spacer(Modifier.height(10.dp))
                    ContentSurface(Modifier.fillMaxWidth()) {
                        Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
                            Text(bug.description.orEmpty(), style = MaterialTheme.typography.bodyLarge)
                            if (!bug.reproductionSteps.isNullOrBlank()) {
                                Text("复现步骤", style = MaterialTheme.typography.titleMedium)
                                Text(bug.reproductionSteps, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                            if (!bug.deviceModel.isNullOrBlank()) {
                                Text(
                                    "${bug.deviceModel} · Android ${bug.androidVersion.orEmpty()} · 客户端 ${bug.clientVersion.orEmpty()}",
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                            }
                        }
                    }
                }
            } else {
                item {
                    InlineMessage("同组反馈只显示标题和处理状态；详细描述与截图仅报告人和管理员可见。")
                }
            }
            if (bug.attachments.isNotEmpty()) {
                item { SectionHeading("截图证据") }
                item {
                    LazyRow(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        items(bug.attachments, key = { it.id }) { attachment ->
                            PrivateImage(
                                repository,
                                attachment.url,
                                "Bug 截图",
                                Modifier
                                    .width(210.dp)
                                    .height(360.dp)
                                    .clip(RoundedCornerShape(18.dp))
                                    .clickable(onClickLabel = "全屏查看截图证据") {
                                        expandedAttachment = attachment.url
                                    },
                                contentScale = ContentScale.Fit,
                                cacheInMemory = false,
                            )
                        }
                    }
                }
            }
            if (bug.resolutionNote.isNotBlank()) {
                item {
                    Surface(
                        color = MaterialTheme.colorScheme.secondaryContainer,
                        shape = RoundedCornerShape(18.dp),
                    ) {
                        Row(Modifier.padding(18.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                            Icon(Icons.Rounded.CheckCircle, null, tint = MaterialTheme.colorScheme.secondary)
                            Column {
                                Text("处理结论", style = MaterialTheme.typography.titleMedium)
                                Text(bug.resolutionNote)
                            }
                        }
                    }
                }
            }
            if (bug.status == BugState.VERIFYING && isReporter) {
                item {
                    SectionHeading("验证修复", supporting = "管理员已关联修复版本，请在安装后确认结果")
                    Spacer(Modifier.height(10.dp))
                    ContentSurface(Modifier.fillMaxWidth()) {
                        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                            OutlinedTextField(
                                value = verificationNote,
                                onValueChange = { if (it.length <= 5000) verificationNote = it },
                                modifier = Modifier.fillMaxWidth(),
                                label = { Text("验证说明（可选）") },
                                minLines = 2,
                            )
                            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                                Button(
                                    onClick = { onVerify(true, verificationNote) },
                                    enabled = !loading && !commentBusy && !editBusy,
                                    modifier = Modifier.weight(1f),
                                ) { Text("验证通过") }
                                OutlinedButton(
                                    onClick = { onVerify(false, verificationNote) },
                                    enabled = !loading && !commentBusy && !editBusy,
                                    modifier = Modifier.weight(1f),
                                ) { Text("仍有问题") }
                            }
                        }
                    }
                }
            }
            if (bug.comments.isNotEmpty()) {
                item { SectionHeading("讨论记录") }
                items(bug.comments, key = { it.id }) { item ->
                    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text(item.authorName, style = MaterialTheme.typography.labelLarge)
                        Text(item.content, style = MaterialTheme.typography.bodyLarge)
                    }
                }
            }
            if (isReporter) {
                item {
                    ContentSurface(Modifier.fillMaxWidth()) {
                    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Icon(Icons.Rounded.MailOutline, null)
                            Text("补充信息", style = MaterialTheme.typography.titleMedium)
                        }
                        OutlinedTextField(
                            value = comment,
                            onValueChange = { if (it.length <= 5000) comment = it },
                            modifier = Modifier.fillMaxWidth(),
                            label = { Text("公开评论") },
                            minLines = 2,
                        )
                        Button(
                            onClick = { onComment(comment) },
                            enabled = comment.isNotBlank() && !loading && !commentBusy && !editBusy,
                            modifier = Modifier.align(Alignment.End),
                        ) { Text(if (commentBusy) "发送中" else "发送评论") }
                    }
                    }
                }
            }
        }
    }
}
