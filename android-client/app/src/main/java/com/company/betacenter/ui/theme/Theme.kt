package com.company.betacenter.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val LightColors = lightColorScheme(
    primary = PrimaryLight,
    onPrimary = Color.White,
    primaryContainer = PrimaryContainerLight,
    onPrimaryContainer = Color(0xFF102466),
    secondary = PublishedLight,
    onSecondary = Color.White,
    secondaryContainer = Color(0xFFC1F0DF),
    onSecondaryContainer = Color(0xFF002118),
    tertiary = PendingLight,
    background = CanvasLight,
    onBackground = InkLight,
    surface = SurfaceLight,
    onSurface = InkLight,
    surfaceVariant = SurfaceContainerLight,
    onSurfaceVariant = InkSoftLight,
    outline = Color(0xFF707B76),
    outlineVariant = Color(0xFFC3CBC7),
    error = ErrorLight,
    onError = Color.White,
)

private val DarkColors = darkColorScheme(
    primary = PrimaryDark,
    onPrimary = Color(0xFF102466),
    primaryContainer = PrimaryContainerDark,
    onPrimaryContainer = Color(0xFFDDE4FF),
    secondary = PublishedDark,
    onSecondary = Color(0xFF003829),
    secondaryContainer = Color(0xFF00513C),
    onSecondaryContainer = Color(0xFFB8F2DD),
    tertiary = PendingDark,
    background = CanvasDark,
    onBackground = InkDark,
    surface = SurfaceDark,
    onSurface = InkDark,
    surfaceVariant = SurfaceContainerDark,
    onSurfaceVariant = InkSoftDark,
    outline = Color(0xFF89938E),
    outlineVariant = Color(0xFF3D4742),
    error = ErrorDark,
    onError = Color(0xFF690005),
)

@Composable
fun BetaCenterTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    MaterialTheme(
        colorScheme = if (darkTheme) DarkColors else LightColors,
        typography = BetaTypography,
        content = content,
    )
}
