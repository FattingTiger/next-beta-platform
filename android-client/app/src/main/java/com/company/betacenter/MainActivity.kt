package com.company.betacenter

import android.content.Intent
import android.os.Bundle
import android.provider.Settings
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.togetherWith
import androidx.compose.animation.core.tween
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Build
import androidx.compose.material.icons.rounded.Home
import androidx.compose.material.icons.rounded.Person
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.FileProvider
import androidx.core.net.toUri
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.company.betacenter.ui.MainViewModel
import com.company.betacenter.ui.SessionPhase
import com.company.betacenter.ui.UiEffect
import com.company.betacenter.ui.components.ClientUpdatePromptHost
import com.company.betacenter.ui.screens.AppDetailScreen
import com.company.betacenter.ui.screens.AppListScreen
import com.company.betacenter.ui.screens.BugDetailScreen
import com.company.betacenter.ui.screens.BugListScreen
import com.company.betacenter.ui.screens.BugReportScreen
import com.company.betacenter.ui.screens.InitialPasswordScreen
import com.company.betacenter.ui.screens.LoginScreen
import com.company.betacenter.ui.screens.ProfileScreen
import com.company.betacenter.ui.theme.BetaCenterTheme
import java.io.File

class MainActivity : ComponentActivity() {
    private val viewModel: MainViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            BetaCenterTheme {
                Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
                    BetaCenterRoot(viewModel)
                }
            }
        }
    }

    override fun onResume() {
        super.onResume()
        viewModel.refreshSelectedAppInstallation()
    }
}

private const val ROUTE_HOME = "home"
private const val ROUTE_BUGS = "bugs"
private const val ROUTE_PROFILE = "profile"
private const val ROUTE_DETAIL = "detail"
private const val ROUTE_REPORT = "report"
private const val ROUTE_BUG_DETAIL = "bug-detail"

private fun itemRequestKey(userId: String, itemId: String): String = "$userId\u0000$itemId"

private fun bugListRequestKey(userId: String, mine: Boolean, appId: String?): String =
    "$userId\u0000$mine\u0000${appId.orEmpty()}"

@Composable
private fun BetaCenterRoot(viewModel: MainViewModel) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    var route by rememberSaveable { mutableStateOf(ROUTE_HOME) }
    var navigationUserId by rememberSaveable { mutableStateOf<String?>(null) }
    var activeAppId by rememberSaveable { mutableStateOf<String?>(null) }
    var activeBugId by rememberSaveable { mutableStateOf<String?>(null) }
    var bugScopeMine by rememberSaveable { mutableStateOf(true) }
    var bugScopeAppId by rememberSaveable { mutableStateOf<String?>(null) }
    var bugScopeAppName by rememberSaveable { mutableStateOf<String?>(null) }
    var appRestoreRequestKey by remember { mutableStateOf<String?>(null) }
    var appLoadingObservedKey by remember { mutableStateOf<String?>(null) }
    var bugRestoreRequestKey by remember { mutableStateOf<String?>(null) }
    var bugLoadingObservedKey by remember { mutableStateOf<String?>(null) }
    var bugsRestoreRequestKey by remember { mutableStateOf<String?>(null) }
    val context = LocalContext.current
    var pendingInstallPath by remember { mutableStateOf<String?>(null) }

    fun openInstaller(path: String) {
        val file = File(path)
        if (!file.isFile) {
            viewModel.downloadedFileMissing()
            Toast.makeText(context, "下载文件不存在，请重新下载", Toast.LENGTH_LONG).show()
            return
        }
        runCatching {
            val uri = FileProvider.getUriForFile(context, "${context.packageName}.files", file)
            context.startActivity(
                Intent(Intent.ACTION_VIEW).apply {
                    setDataAndType(uri, "application/vnd.android.package-archive")
                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                },
            )
        }.onFailure {
            Toast.makeText(context, "无法打开系统安装界面", Toast.LENGTH_LONG).show()
        }
    }

    val settingsLauncher = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) {
        val pending = pendingInstallPath
        if (pending != null && context.packageManager.canRequestPackageInstalls()) {
            pendingInstallPath = null
            openInstaller(pending)
        } else if (pending != null) {
            Toast.makeText(context, "允许安装后，请再次点“安装应用”", Toast.LENGTH_LONG).show()
        }
    }

    val signedInUserId = (state.session as? SessionPhase.SignedIn)?.session?.user?.id

    LaunchedEffect(
        signedInUserId,
        navigationUserId,
        route,
        activeAppId,
        activeBugId,
        bugScopeMine,
        bugScopeAppId,
        bugScopeAppName,
        state.detailLoading,
        state.selectedApp?.id,
        state.bugLoading,
        state.selectedBug?.id,
        state.bugsLoading,
        state.bugListMine,
        state.bugListAppId,
        state.myBugs.size,
        state.bugTotal,
    ) {
        if (signedInUserId == null) {
            route = ROUTE_HOME
            navigationUserId = null
            activeAppId = null
            activeBugId = null
            bugScopeMine = true
            bugScopeAppId = null
            bugScopeAppName = null
            appRestoreRequestKey = null
            appLoadingObservedKey = null
            bugRestoreRequestKey = null
            bugLoadingObservedKey = null
            bugsRestoreRequestKey = null
            pendingInstallPath = null
            return@LaunchedEffect
        }

        if (navigationUserId == null) {
            // A route without an owner can come from state saved by an older app
            // version. Do not risk restoring one account's route into another.
            if (route != ROUTE_HOME) {
                route = ROUTE_HOME
                activeAppId = null
                activeBugId = null
                bugScopeMine = true
                bugScopeAppId = null
                bugScopeAppName = null
            }
            navigationUserId = signedInUserId
            return@LaunchedEffect
        }

        if (navigationUserId != signedInUserId) {
            route = ROUTE_HOME
            navigationUserId = signedInUserId
            activeAppId = null
            activeBugId = null
            bugScopeMine = true
            bugScopeAppId = null
            bugScopeAppName = null
            appRestoreRequestKey = null
            appLoadingObservedKey = null
            bugRestoreRequestKey = null
            bugLoadingObservedKey = null
            bugsRestoreRequestKey = null
            pendingInstallPath = null
            return@LaunchedEffect
        }

        when (route) {
            ROUTE_DETAIL, ROUTE_REPORT -> {
                val appId = activeAppId
                if (appId == null) {
                    route = ROUTE_HOME
                    return@LaunchedEffect
                }
                val requestKey = itemRequestKey(signedInUserId, appId)
                when {
                    state.selectedApp?.id == appId -> appRestoreRequestKey = requestKey
                    state.detailLoading -> appLoadingObservedKey = requestKey
                    appRestoreRequestKey != requestKey -> {
                        appRestoreRequestKey = requestKey
                        viewModel.openApp(appId)
                        // openApp marks detailLoading synchronously. Record the
                        // attempt here as well so even an extremely fast failure
                        // cannot strand the restored destination on a spinner.
                        appLoadingObservedKey = requestKey
                    }
                    appLoadingObservedKey == requestKey -> {
                        // A single restore attempt failed. Keep the error message,
                        // but leave the loading-only destination instead of retrying.
                        activeAppId = null
                        viewModel.clearSelectedApp()
                        route = ROUTE_HOME
                    }
                    else -> Unit
                }
            }
            ROUTE_BUG_DETAIL -> {
                val bugId = activeBugId
                if (bugId == null) {
                    route = ROUTE_BUGS
                    return@LaunchedEffect
                }
                val requestKey = itemRequestKey(signedInUserId, bugId)
                when {
                    state.selectedBug?.id == bugId -> bugRestoreRequestKey = requestKey
                    state.bugLoading -> bugLoadingObservedKey = requestKey
                    bugRestoreRequestKey != requestKey -> {
                        bugRestoreRequestKey = requestKey
                        viewModel.loadBug(bugId)
                        bugLoadingObservedKey = requestKey
                    }
                    bugLoadingObservedKey == requestKey -> {
                        activeBugId = null
                        route = ROUTE_BUGS
                    }
                    else -> Unit
                }
            }
            ROUTE_BUGS -> {
                val requestKey = bugListRequestKey(signedInUserId, bugScopeMine, bugScopeAppId)
                val queryMatches =
                    state.bugListMine == bugScopeMine && state.bugListAppId == bugScopeAppId
                when {
                    bugsRestoreRequestKey == requestKey -> Unit
                    queryMatches &&
                        (state.bugsLoading || state.myBugs.isNotEmpty() || state.bugTotal > 0) -> {
                        bugsRestoreRequestKey = requestKey
                    }
                    else -> {
                        bugsRestoreRequestKey = requestKey
                        val appId = bugScopeAppId
                        if (appId == null) {
                            viewModel.loadAllBugs(bugScopeMine)
                        } else {
                            viewModel.loadBugsForApp(
                                appId,
                                bugScopeAppName ?: "指定应用",
                            )
                            // loadBugsForApp establishes the app scope. Reapply the
                            // saved ownership filter when it differs from its default.
                            if (bugScopeMine) viewModel.loadBugs(mine = true)
                        }
                    }
                }
            }
        }
    }
    LaunchedEffect(Unit) {
        viewModel.effects.collect { effect ->
            when (effect) {
                is UiEffect.BugSubmitted -> {
                    activeBugId = effect.bugId
                    val requestKey = navigationUserId?.let {
                        itemRequestKey(it, effect.bugId)
                    }
                    bugRestoreRequestKey = requestKey
                    viewModel.loadBug(effect.bugId)
                    bugLoadingObservedKey = requestKey
                    route = ROUTE_BUG_DETAIL
                }
                is UiEffect.OpenInstaller -> {
                    if (context.packageManager.canRequestPackageInstalls()) {
                        openInstaller(effect.filePath)
                    } else {
                        pendingInstallPath = effect.filePath
                        settingsLauncher.launch(
                            Intent(
                                Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                                "package:${context.packageName}".toUri(),
                            ),
                        )
                    }
                }
                is UiEffect.OpenInstalledApp -> {
                    val launchIntent = context.packageManager.getLaunchIntentForPackage(effect.packageName)
                    if (launchIntent == null) {
                        viewModel.refreshSelectedAppInstallation()
                        Toast.makeText(context, "应用已安装，但没有可打开的启动页面", Toast.LENGTH_LONG).show()
                    } else {
                        context.startActivity(launchIntent)
                    }
                }
            }
        }
    }

    when (val session = state.session) {
        SessionPhase.SignedOut -> LoginScreen(
            busy = state.loginBusy,
            message = state.message,
            messageIsError = state.messageIsError,
            onLogin = viewModel::login,
            onDismissMessage = viewModel::dismissMessage,
        )
        is SessionPhase.PasswordChangeRequired -> InitialPasswordScreen(
            displayName = session.session.user.displayName,
            busy = state.loginBusy,
            message = state.message,
            messageIsError = state.messageIsError,
            onSubmit = viewModel::changeInitialPassword,
            onDismissMessage = viewModel::dismissMessage,
        )
        is SessionPhase.SignedIn -> {
            BackHandler(enabled = route !in setOf(ROUTE_HOME, ROUTE_BUGS, ROUTE_PROFILE)) {
                when (route) {
                    ROUTE_REPORT -> route = ROUTE_DETAIL
                    ROUTE_BUG_DETAIL -> {
                        activeBugId = null
                        route = ROUTE_BUGS
                    }
                    else -> {
                        activeAppId = null
                        viewModel.clearSelectedApp()
                        route = ROUTE_HOME
                    }
                }
            }
            val mainTab = route in setOf(ROUTE_HOME, ROUTE_BUGS, ROUTE_PROFILE)
            Scaffold(
                bottomBar = {
                    if (mainTab) {
                        NavigationBar(containerColor = MaterialTheme.colorScheme.surface.copy(alpha = 0.98f)) {
                            NavigationBarItem(
                                selected = route == ROUTE_HOME,
                                onClick = {
                                    activeAppId = null
                                    activeBugId = null
                                    viewModel.clearSelectedApp()
                                    route = ROUTE_HOME
                                },
                                icon = { Icon(Icons.Rounded.Home, null) },
                                label = { Text("应用") },
                            )
                            NavigationBarItem(
                                selected = route == ROUTE_BUGS,
                                onClick = {
                                    activeBugId = null
                                    bugScopeMine = state.bugListMine
                                    bugScopeAppId = null
                                    bugScopeAppName = null
                                    bugsRestoreRequestKey = bugListRequestKey(
                                        session.session.user.id,
                                        bugScopeMine,
                                        null,
                                    )
                                    route = ROUTE_BUGS
                                    viewModel.loadAllBugs(bugScopeMine)
                                },
                                icon = { Icon(Icons.Rounded.Build, null) },
                                label = { Text("反馈") },
                            )
                            NavigationBarItem(
                                selected = route == ROUTE_PROFILE,
                                onClick = {
                                    activeAppId = null
                                    activeBugId = null
                                    viewModel.clearSelectedApp()
                                    route = ROUTE_PROFILE
                                },
                                icon = { Icon(Icons.Rounded.Person, null) },
                                label = { Text("我的") },
                            )
                        }
                    }
                },
            ) { padding ->
                AnimatedContent(
                    targetState = route,
                    modifier = Modifier.padding(if (mainTab) padding else androidx.compose.foundation.layout.PaddingValues()),
                    transitionSpec = { fadeIn(tween(200)) togetherWith fadeOut(tween(160)) },
                    label = "main-navigation",
                ) { activeRoute ->
                    when (activeRoute) {
                        ROUTE_HOME -> AppListScreen(
                            repository = viewModel.repository,
                            displayName = session.session.user.displayName,
                            apps = state.apps,
                            loading = state.appsLoading,
                            initialSearch = state.search,
                            message = state.message,
                            messageIsError = state.messageIsError,
                            onSearch = viewModel::refreshApps,
                            onRefresh = { viewModel.refreshApps() },
                            onOpenApp = { appId ->
                                activeAppId = appId
                                val requestKey = itemRequestKey(session.session.user.id, appId)
                                appRestoreRequestKey = requestKey
                                viewModel.openApp(appId)
                                appLoadingObservedKey = requestKey
                                route = ROUTE_DETAIL
                            },
                            onDismissMessage = viewModel::dismissMessage,
                        )
                        ROUTE_BUGS -> BugListScreen(
                            bugs = state.myBugs,
                            mine = state.bugListMine,
                            appScopeName = state.bugListAppName,
                            total = state.bugTotal,
                            loading = state.bugsLoading,
                            loadingMore = state.bugsLoadingMore,
                            message = state.message,
                            messageIsError = state.messageIsError,
                            onModeChange = { mine ->
                                bugScopeMine = mine
                                bugsRestoreRequestKey = bugListRequestKey(
                                    session.session.user.id,
                                    mine,
                                    bugScopeAppId,
                                )
                                viewModel.loadBugs(mine)
                            },
                            onOpenBug = { bugId ->
                                activeBugId = bugId
                                val requestKey = itemRequestKey(session.session.user.id, bugId)
                                bugRestoreRequestKey = requestKey
                                viewModel.loadBug(bugId)
                                bugLoadingObservedKey = requestKey
                                route = ROUTE_BUG_DETAIL
                            },
                            onRefresh = {
                                bugsRestoreRequestKey = bugListRequestKey(
                                    session.session.user.id,
                                    bugScopeMine,
                                    bugScopeAppId,
                                )
                                viewModel.loadBugs(bugScopeMine)
                            },
                            onLoadMore = viewModel::loadMoreBugs,
                            onDismissMessage = viewModel::dismissMessage,
                        )
                        ROUTE_PROFILE -> ProfileScreen(session.session.user, viewModel::logout)
                        ROUTE_DETAIL -> state.selectedApp?.let { app ->
                            AppDetailScreen(
                                repository = viewModel.repository,
                                app = app,
                                bugCounts = state.selectedAppBugCounts,
                                download = state.download,
                                installation = state.installation,
                                message = state.message,
                                messageIsError = state.messageIsError,
                                onBack = {
                                    activeAppId = null
                                    viewModel.clearSelectedApp()
                                    route = ROUTE_HOME
                                },
                                onDownload = viewModel::startDownload,
                                onCancelDownload = viewModel::cancelDownload,
                                onInstall = viewModel::installDownloadedApk,
                                onOpenInstalledApp = viewModel::openInstalledApp,
                                onReportBug = { route = ROUTE_REPORT },
                                onViewBugs = {
                                    activeBugId = null
                                    bugScopeMine = false
                                    bugScopeAppId = app.id
                                    bugScopeAppName = app.name
                                    bugsRestoreRequestKey = bugListRequestKey(
                                        session.session.user.id,
                                        mine = false,
                                        appId = app.id,
                                    )
                                    viewModel.loadBugsForApp(app.id, app.name)
                                    route = ROUTE_BUGS
                                },
                                onDismissMessage = viewModel::dismissMessage,
                            )
                        } ?: LoadingScreen()
                        ROUTE_REPORT -> state.selectedApp?.let { app ->
                            BugReportScreen(
                                repository = viewModel.repository,
                                draftStore = viewModel.bugDraftStore,
                                userId = session.session.user.id,
                                app = app,
                                submitting = state.submittingBug,
                                message = state.message,
                                messageIsError = state.messageIsError,
                                onBack = { route = ROUTE_DETAIL },
                                onSubmit = viewModel::submitBug,
                                onDismissMessage = viewModel::dismissMessage,
                            )
                        } ?: LoadingScreen()
                        ROUTE_BUG_DETAIL -> state.selectedBug?.let { bug ->
                            BugDetailScreen(
                                repository = viewModel.repository,
                                currentUserId = session.session.user.id,
                                bug = bug,
                                loading = state.bugLoading,
                                editBusy = state.bugEditBusy,
                                editSubmitSequence = state.bugEditSubmitSequence,
                                commentBusy = state.commentBusy,
                                commentSubmitSequence = state.commentSubmitSequence,
                                message = state.message,
                                messageIsError = state.messageIsError,
                                onBack = {
                                    activeBugId = null
                                    route = ROUTE_BUGS
                                },
                                onEdit = viewModel::updateBugText,
                                onComment = viewModel::addComment,
                                onVerify = viewModel::verifyBug,
                                onDismissMessage = viewModel::dismissMessage,
                            )
                        } ?: LoadingScreen()
                        else -> LoadingScreen()
                    }
                }
            }
        }
    }
    ClientUpdatePromptHost()
}

@Composable
private fun LoadingScreen() {
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        CircularProgressIndicator()
    }
}
