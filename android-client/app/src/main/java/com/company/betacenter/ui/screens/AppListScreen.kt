package com.company.betacenter.ui.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowForward
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusManager
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.company.betacenter.data.AppCard
import com.company.betacenter.data.BetaRepository
import com.company.betacenter.ui.components.AuroraBackdrop
import com.company.betacenter.ui.components.InlineMessage
import com.company.betacenter.ui.components.LensSurface
import com.company.betacenter.ui.components.PrivateImage
import com.company.betacenter.ui.components.SectionHeading
import kotlinx.coroutines.delay

@Composable
fun AppListScreen(
    repository: BetaRepository,
    displayName: String,
    apps: List<AppCard>,
    loading: Boolean,
    initialSearch: String,
    message: String?,
    messageIsError: Boolean,
    onSearch: (String) -> Unit,
    onRefresh: () -> Unit,
    onOpenApp: (String) -> Unit,
    onDismissMessage: () -> Unit,
) {
    var search by remember(initialSearch) { mutableStateOf(initialSearch) }
    val focusManager = LocalFocusManager.current
    LaunchedEffect(search) {
        delay(350)
        if (search != initialSearch) onSearch(search)
    }
    Box(Modifier.fillMaxSize()) {
        AuroraBackdrop(
            Modifier
                .fillMaxWidth()
                .height(300.dp),
        )
        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = androidx.compose.foundation.layout.PaddingValues(
                start = 20.dp,
                top = 34.dp,
                end = 20.dp,
                bottom = 28.dp,
            ),
            verticalArrangement = Arrangement.spacedBy(20.dp),
        ) {
            item {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("你好，$displayName", style = MaterialTheme.typography.bodyLarge)
                        Text("内测中心", style = MaterialTheme.typography.headlineLarge)
                    }
                    IconButton(onClick = onRefresh, enabled = !loading) {
                        Icon(Icons.Rounded.Refresh, contentDescription = "刷新应用")
                    }
                }
            }
            if (message != null) {
                item {
                    InlineMessage(
                        message = message,
                        isError = messageIsError,
                        actionLabel = if (messageIsError) "关闭" else null,
                        onAction = onDismissMessage,
                    )
                }
            }
            item {
                SearchField(search, focusManager, onValueChange = { search = it })
            }
            if (loading && apps.isEmpty()) {
                item {
                    Box(Modifier.fillMaxWidth().height(180.dp), contentAlignment = Alignment.Center) {
                        CircularProgressIndicator()
                    }
                }
            } else if (apps.isEmpty()) {
                item {
                    EmptyCatalog(hasSearch = search.isNotBlank(), onClear = {
                        search = ""
                        onSearch("")
                    })
                }
            } else {
                item {
                    FeaturedRelease(repository, apps.first(), onOpenApp)
                }
                if (apps.size > 1) {
                    item { SectionHeading("全部应用", supporting = "仅显示你所在测试组可见的版本") }
                    items(apps.drop(1), key = AppCard::id) { app ->
                        AppRow(repository, app, onOpenApp)
                        HorizontalDivider(
                            modifier = Modifier.padding(start = 84.dp, top = 14.dp),
                            color = MaterialTheme.colorScheme.outlineVariant,
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun SearchField(value: String, focusManager: FocusManager, onValueChange: (String) -> Unit) {
    OutlinedTextField(
        value = value,
        onValueChange = { if (it.length <= 100) onValueChange(it) },
        modifier = Modifier.fillMaxWidth(),
        singleLine = true,
        label = { Text("搜索应用") },
        leadingIcon = { Icon(Icons.Rounded.Search, null) },
        keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
        keyboardActions = KeyboardActions(onSearch = { focusManager.clearFocus() }),
        shape = RoundedCornerShape(16.dp),
    )
}

@Composable
private fun FeaturedRelease(
    repository: BetaRepository,
    app: AppCard,
    onOpenApp: (String) -> Unit,
) {
    LensSurface(Modifier.fillMaxWidth()) {
        Column(verticalArrangement = Arrangement.spacedBy(18.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(16.dp), verticalAlignment = Alignment.CenterVertically) {
                PrivateImage(
                    repository = repository,
                    relativeUrl = app.iconUrl,
                    contentDescription = "${app.name} 图标",
                    modifier = Modifier.size(76.dp).clip(RoundedCornerShape(20.dp)),
                )
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(app.name, style = MaterialTheme.typography.headlineMedium, maxLines = 2)
                    Text(
                        "版本 ${app.currentVersion?.versionName ?: "—"}",
                        style = MaterialTheme.typography.labelLarge,
                        color = MaterialTheme.colorScheme.primary,
                    )
                    Text(
                        app.shortDescription.ifBlank { "等待你的测试反馈" },
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
            }
            val release = app.currentVersion?.releaseNotes.orEmpty()
            if (release.isNotBlank()) {
                Text(
                    release,
                    style = MaterialTheme.typography.bodyLarge,
                    maxLines = 3,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            Button(onClick = { onOpenApp(app.id) }, modifier = Modifier.fillMaxWidth().height(50.dp)) {
                Text("查看当前版本")
                Spacer(Modifier.size(8.dp))
                Icon(Icons.AutoMirrored.Rounded.ArrowForward, null, Modifier.size(19.dp))
            }
        }
    }
}

@Composable
private fun AppRow(repository: BetaRepository, app: AppCard, onOpenApp: (String) -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClickLabel = "查看 ${app.name}") { onOpenApp(app.id) }
            .padding(vertical = 6.dp),
        horizontalArrangement = Arrangement.spacedBy(14.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        PrivateImage(
            repository,
            app.iconUrl,
            "${app.name} 图标",
            Modifier.size(64.dp).clip(RoundedCornerShape(17.dp)),
        )
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Text(app.name, style = MaterialTheme.typography.titleMedium, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(
                app.shortDescription,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                "v${app.currentVersion?.versionName ?: "—"}",
                style = MaterialTheme.typography.labelMedium,
                fontWeight = FontWeight.SemiBold,
                color = MaterialTheme.colorScheme.primary,
            )
        }
        Icon(
            Icons.AutoMirrored.Rounded.ArrowForward,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun EmptyCatalog(hasSearch: Boolean, onClear: () -> Unit) {
    Column(
        modifier = Modifier.fillMaxWidth().padding(vertical = 52.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Text(if (hasSearch) "没有匹配的应用" else "暂时没有分配给你的应用", style = MaterialTheme.typography.titleLarge)
        Text(
            if (hasSearch) "换个名称试试" else "管理员发布并分配测试组后会显示在这里",
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        if (hasSearch) Button(onClick = onClear) { Text("清除搜索") }
    }
}
