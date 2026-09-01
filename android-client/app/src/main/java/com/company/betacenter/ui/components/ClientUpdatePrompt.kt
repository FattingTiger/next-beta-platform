package com.company.betacenter.ui.components

import android.content.Intent
import android.widget.Toast
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.net.toUri
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.company.betacenter.BetaCenterApplication
import com.company.betacenter.BuildConfig

@Composable
fun ClientUpdatePromptHost() {
    val context = LocalContext.current
    val manager = remember(context.applicationContext) {
        (context.applicationContext as BetaCenterApplication).container.clientUpdateManager
    }
    val update by manager.availableUpdate.collectAsStateWithLifecycle()
    var deferredFileName by rememberSaveable { mutableStateOf<String?>(null) }
    val candidate = update?.takeUnless { it.fileName == deferredFileName }

    candidate?.let { available ->
        AlertDialog(
            onDismissRequest = { deferredFileName = available.fileName },
            icon = { Icon(Icons.Rounded.Refresh, contentDescription = null) },
            title = { Text("发现新版本 ${available.version}") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("当前版本 ${BuildConfig.VERSION_NAME}，建议更新后继续参与内测。")
                    if (available.releaseNotes.isNotBlank()) {
                        Spacer(Modifier.height(2.dp))
                        Text(available.releaseNotes, style = MaterialTheme.typography.bodyMedium)
                    }
                    Text(
                        "安装包约 ${formatFileSize(available.fileSize)}，点击后通过浏览器下载。",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            },
            dismissButton = {
                TextButton(onClick = { deferredFileName = available.fileName }) { Text("稍后") }
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        val opened = runCatching {
                            context.startActivity(
                                Intent(Intent.ACTION_VIEW, available.downloadUrl.toUri()).apply {
                                    addCategory(Intent.CATEGORY_BROWSABLE)
                                },
                            )
                        }.isSuccess
                        if (opened) {
                            deferredFileName = available.fileName
                        } else {
                            Toast.makeText(context, "无法打开下载链接", Toast.LENGTH_LONG).show()
                        }
                    },
                ) { Text("下载更新") }
            },
        )
    }
}

private fun formatFileSize(bytes: Long): String =
    if (bytes >= 1024L * 1024L) {
        "%.1f MB".format(bytes.toDouble() / (1024L * 1024L))
    } else {
        "%.0f KB".format(bytes.toDouble() / 1024L)
    }
