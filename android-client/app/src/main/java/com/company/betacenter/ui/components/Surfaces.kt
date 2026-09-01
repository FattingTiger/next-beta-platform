package com.company.betacenter.ui.components

import android.os.Build
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.border
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.blur
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

val LensShape = RoundedCornerShape(30.dp)
val ContentShape = RoundedCornerShape(20.dp)
val CompactShape = RoundedCornerShape(16.dp)
val ControlShape = RoundedCornerShape(14.dp)

@Composable
fun AuroraBackdrop(
    modifier: Modifier = Modifier,
    content: @Composable BoxScope.() -> Unit = {},
) {
    val primary = MaterialTheme.colorScheme.primary
    val secondary = MaterialTheme.colorScheme.secondary
    val dark = isSystemInDarkTheme()
    Box(modifier = modifier.clip(RoundedCornerShape(bottomStart = 40.dp, bottomEnd = 40.dp))) {
        Canvas(
            modifier = Modifier
                .fillMaxSize()
                .then(if (Build.VERSION.SDK_INT >= 31) Modifier.blur(14.dp) else Modifier),
        ) {
            drawRect(
                brush = Brush.linearGradient(
                    colors = listOf(
                        primary.copy(alpha = if (dark) 0.38f else 0.30f),
                        secondary.copy(alpha = if (dark) 0.28f else 0.20f),
                        Color.Transparent,
                    ),
                    start = Offset.Zero,
                    end = Offset(size.width, size.height),
                ),
            )
            drawOval(
                color = primary.copy(alpha = if (dark) 0.20f else 0.16f),
                topLeft = Offset(size.width * 0.55f, -size.height * 0.28f),
                size = Size(size.width * 0.72f, size.height * 0.86f),
            )
        }
        content()
    }
}

@Composable
fun LensSurface(
    modifier: Modifier = Modifier,
    contentPadding: PaddingValues = PaddingValues(22.dp),
    content: @Composable BoxScope.() -> Unit,
) {
    val dark = isSystemInDarkTheme()
    val outline = MaterialTheme.colorScheme.outlineVariant.copy(alpha = if (dark) 0.72f else 0.78f)
    Surface(
        modifier = modifier.border(1.dp, outline, LensShape),
        shape = LensShape,
        color = MaterialTheme.colorScheme.surface.copy(
            alpha = when {
                Build.VERSION.SDK_INT < 31 -> if (dark) 0.98f else 0.99f
                dark -> 0.88f
                else -> 0.84f
            },
        ),
        contentColor = MaterialTheme.colorScheme.onSurface,
    ) {
        Box(Modifier.padding(contentPadding), content = content)
    }
}

@Composable
fun ContentSurface(
    modifier: Modifier = Modifier,
    contentPadding: PaddingValues = PaddingValues(20.dp),
    content: @Composable BoxScope.() -> Unit,
) {
    Surface(
        modifier = modifier,
        shape = ContentShape,
        color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = if (isSystemInDarkTheme()) 0.94f else 0.96f),
        contentColor = MaterialTheme.colorScheme.onSurface,
        tonalElevation = 1.dp,
    ) {
        Box(Modifier.padding(contentPadding), content = content)
    }
}
