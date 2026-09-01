package com.company.betacenter.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material.icons.rounded.Info
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.company.betacenter.data.BugState
import com.company.betacenter.ui.theme.PendingDark
import com.company.betacenter.ui.theme.PendingLight
import com.company.betacenter.ui.theme.ProgressDark
import com.company.betacenter.ui.theme.ProgressLight
import com.company.betacenter.ui.theme.PublishedDark
import com.company.betacenter.ui.theme.PublishedLight

@Composable
fun InlineMessage(
    message: String,
    modifier: Modifier = Modifier,
    isError: Boolean = false,
    actionLabel: String? = null,
    onAction: (() -> Unit)? = null,
) {
    val color = if (isError) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary
    Row(
        modifier = modifier
            .fillMaxWidth()
            .background(color.copy(alpha = 0.10f), CompactShape)
            .padding(horizontal = 14.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Icon(
            if (isError) Icons.Rounded.Warning else Icons.Rounded.Info,
            contentDescription = null,
            tint = color,
            modifier = Modifier.size(20.dp),
        )
        Text(message, modifier = Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium)
        if (actionLabel != null && onAction != null) {
            TextButton(onClick = onAction) {
                Icon(
                    if (actionLabel == "关闭") Icons.Rounded.Close else Icons.Rounded.Refresh,
                    contentDescription = null,
                    modifier = Modifier.size(18.dp),
                )
                Text(actionLabel)
            }
        }
    }
}

@Composable
fun BugStatusPill(status: BugState, modifier: Modifier = Modifier) {
    val dark = androidx.compose.foundation.isSystemInDarkTheme()
    val (label, color) = when (status) {
        BugState.PENDING -> "待处理" to if (dark) PendingDark else PendingLight
        BugState.IN_PROGRESS -> "处理中" to if (dark) ProgressDark else ProgressLight
        BugState.VERIFYING -> "待验证" to MaterialTheme.colorScheme.primary
        BugState.CLOSED -> "已关闭" to if (dark) PublishedDark else PublishedLight
        BugState.UNKNOWN -> "状态未知" to MaterialTheme.colorScheme.onSurfaceVariant
    }
    Row(
        modifier = modifier
            .background(color.copy(alpha = 0.13f), CircleShape)
            .padding(horizontal = 10.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Spacer(Modifier.size(7.dp).background(color, CircleShape))
        Text(label, color = color, style = MaterialTheme.typography.labelMedium)
    }
}

@Composable
fun SectionHeading(title: String, modifier: Modifier = Modifier, supporting: String? = null) {
    androidx.compose.foundation.layout.Column(modifier = modifier) {
        Text(title, style = MaterialTheme.typography.titleLarge)
        if (!supporting.isNullOrBlank()) {
            Spacer(Modifier.height(4.dp))
            Text(supporting, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}
