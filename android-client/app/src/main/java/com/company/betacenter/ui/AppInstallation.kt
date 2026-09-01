package com.company.betacenter.ui

import android.content.pm.PackageManager
import android.os.Build
import com.company.betacenter.data.AppDetails

enum class InstalledVersionMatch {
    NOT_INSTALLED,
    OUTDATED,
    CURRENT,
    NEWER,
    INSTALLED_WITHOUT_TARGET,
}

data class AppInstallationUiState(
    val installedVersionCode: Long? = null,
    val installedVersionName: String? = null,
    val canOpen: Boolean = false,
    val match: InstalledVersionMatch = InstalledVersionMatch.NOT_INSTALLED,
) {
    val isInstalled: Boolean get() = installedVersionCode != null
    val isCurrentOrNewer: Boolean
        get() = match == InstalledVersionMatch.CURRENT || match == InstalledVersionMatch.NEWER
}

internal fun classifyInstalledVersion(
    installedVersionCode: Long?,
    targetVersionCode: Long?,
): InstalledVersionMatch = when {
    installedVersionCode == null -> InstalledVersionMatch.NOT_INSTALLED
    targetVersionCode == null -> InstalledVersionMatch.INSTALLED_WITHOUT_TARGET
    installedVersionCode < targetVersionCode -> InstalledVersionMatch.OUTDATED
    installedVersionCode == targetVersionCode -> InstalledVersionMatch.CURRENT
    else -> InstalledVersionMatch.NEWER
}

internal fun inspectAppInstallation(
    packageManager: PackageManager,
    app: AppDetails,
): AppInstallationUiState {
    val info = try {
        if (Build.VERSION.SDK_INT >= 33) {
            packageManager.getPackageInfo(app.packageName, PackageManager.PackageInfoFlags.of(0))
        } else {
            @Suppress("DEPRECATION")
            packageManager.getPackageInfo(app.packageName, 0)
        }
    } catch (_: PackageManager.NameNotFoundException) {
        return AppInstallationUiState()
    } catch (_: SecurityException) {
        return AppInstallationUiState()
    }
    val installedVersionCode = if (Build.VERSION.SDK_INT >= 28) {
        info.longVersionCode
    } else {
        @Suppress("DEPRECATION")
        info.versionCode.toLong()
    }
    return AppInstallationUiState(
        installedVersionCode = installedVersionCode,
        installedVersionName = info.versionName,
        canOpen = packageManager.getLaunchIntentForPackage(app.packageName) != null,
        match = classifyInstalledVersion(installedVersionCode, app.currentVersion?.versionCode),
    )
}
