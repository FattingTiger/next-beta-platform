package com.company.betacenter.ui

import org.junit.Assert.assertEquals
import org.junit.Test

class AppInstallationPolicyTest {
    @Test
    fun classifiesMissingAndUnknownTargetPackages() {
        assertEquals(InstalledVersionMatch.NOT_INSTALLED, classifyInstalledVersion(null, 12L))
        assertEquals(InstalledVersionMatch.INSTALLED_WITHOUT_TARGET, classifyInstalledVersion(11L, null))
    }

    @Test
    fun comparesInstalledVersionAgainstPublishedVersion() {
        assertEquals(InstalledVersionMatch.OUTDATED, classifyInstalledVersion(11L, 12L))
        assertEquals(InstalledVersionMatch.CURRENT, classifyInstalledVersion(12L, 12L))
        assertEquals(InstalledVersionMatch.NEWER, classifyInstalledVersion(13L, 12L))
    }

    @Test
    fun currentOrNewerRequiresAComparableInstalledVersion() {
        assertEquals(false, AppInstallationUiState().isCurrentOrNewer)
        assertEquals(
            true,
            AppInstallationUiState(
                installedVersionCode = 12L,
                match = InstalledVersionMatch.CURRENT,
            ).isCurrentOrNewer,
        )
    }
}
