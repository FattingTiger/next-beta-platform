package com.company.betacenter.ui

import android.app.Application
import android.os.Build
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.work.WorkInfo
import com.company.betacenter.BetaCenterApplication
import com.company.betacenter.data.ApiException
import com.company.betacenter.data.AppCard
import com.company.betacenter.data.AppDetails
import com.company.betacenter.data.AuthSession
import com.company.betacenter.data.BugDraft
import com.company.betacenter.data.BugReport
import com.company.betacenter.data.BugState
import com.company.betacenter.download.DownloadScheduler
import com.company.betacenter.download.KEY_ERROR
import com.company.betacenter.download.KEY_FILE_PATH
import com.company.betacenter.download.KEY_PHASE
import com.company.betacenter.download.KEY_PROGRESS
import com.company.betacenter.download.PHASE_DOWNLOADING
import com.company.betacenter.download.PHASE_PREPARING
import com.company.betacenter.download.PHASE_READY
import com.company.betacenter.download.PHASE_VERIFYING
import com.company.betacenter.ui.components.clearPrivateImageMemoryCache
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.async
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.io.IOException

sealed interface SessionPhase {
    data object SignedOut : SessionPhase
    data class PasswordChangeRequired(val session: AuthSession) : SessionPhase
    data class SignedIn(val session: AuthSession) : SessionPhase
}

enum class DownloadPhase { IDLE, QUEUED, PREPARING, DOWNLOADING, VERIFYING, READY, FAILED }

data class DownloadUiState(
    val phase: DownloadPhase = DownloadPhase.IDLE,
    val progress: Int = 0,
    val filePath: String? = null,
    val error: String? = null,
)

data class MainUiState(
    val session: SessionPhase,
    val loginBusy: Boolean = false,
    val apps: List<AppCard> = emptyList(),
    val appsLoading: Boolean = false,
    val search: String = "",
    val selectedApp: AppDetails? = null,
    val selectedAppBugCounts: Map<BugState, Int> = emptyMap(),
    val detailLoading: Boolean = false,
    val myBugs: List<BugReport> = emptyList(),
    val bugListMine: Boolean = true,
    val bugListAppId: String? = null,
    val bugListAppName: String? = null,
    val bugTotal: Int = 0,
    val bugPage: Int = 1,
    val bugsLoading: Boolean = false,
    val bugsLoadingMore: Boolean = false,
    val selectedBug: BugReport? = null,
    val bugLoading: Boolean = false,
    val bugEditBusy: Boolean = false,
    val bugEditSubmitSequence: Int = 0,
    val commentBusy: Boolean = false,
    val commentSubmitSequence: Int = 0,
    val submittingBug: Boolean = false,
    val download: DownloadUiState = DownloadUiState(),
    val installation: AppInstallationUiState = AppInstallationUiState(),
    val message: String? = null,
    val messageIsError: Boolean = false,
)

sealed interface UiEffect {
    data class BugSubmitted(val bugId: String) : UiEffect
    data class OpenInstaller(val filePath: String) : UiEffect
    data class OpenInstalledApp(val packageName: String) : UiEffect
}

private data class AccountKey(
    val generation: Long,
    val userId: String,
)

private data class BugQueryKey(
    val mine: Boolean,
    val appId: String?,
)

private data class BugMutationKey(
    val account: AccountKey,
    val bugId: String,
)

private enum class BugMutationKind { EDIT, COMMENT, VERIFY }

private class ActiveBugMutation(val kind: BugMutationKind)

class MainViewModel(application: Application) : AndroidViewModel(application) {
    val repository = (application as BetaCenterApplication).container.repository
    val bugDraftStore = (application as BetaCenterApplication).container.bugDraftStore
    private val downloadScheduler = DownloadScheduler(application)

    private val initialSession = repository.currentSession()
    private val initialRetiringSession = repository.retiringSession()
    private val _state = MutableStateFlow(
        MainUiState(
            session = when {
                initialSession == null -> SessionPhase.SignedOut
                initialSession.user.mustChangePassword -> SessionPhase.PasswordChangeRequired(initialSession)
                else -> SessionPhase.SignedIn(initialSession)
            },
        ),
    )
    val state: StateFlow<MainUiState> = _state.asStateFlow()

    private val _effects = MutableSharedFlow<UiEffect>(extraBufferCapacity = 4)
    val effects: SharedFlow<UiEffect> = _effects.asSharedFlow()

    private var accountGeneration = if (initialSession == null) 0L else 1L
    private var accountRootJob = SupervisorJob(viewModelScope.coroutineContext[Job])
    private var accountScope = CoroutineScope(viewModelScope.coroutineContext + accountRootJob)
    private var authAttempt = 0L
    private var authJob: Job? = null
    private var downloadCleanupJob: Job? = null

    private var downloadObserver: Job? = null
    private var appsJob: Job? = null
    private var detailJob: Job? = null
    private var bugsJob: Job? = null
    private var bugDetailJob: Job? = null
    private var appsRevision = 0L
    private var detailRevision = 0L
    private var bugQueryRevision = 0L
    private var bugDetailRevision = 0L
    private val activeBugMutations = mutableMapOf<BugMutationKey, ActiveBugMutation>()

    init {
        initialRetiringSession?.let { retiring ->
            scheduleDownloadCleanup(
                userId = retiring.user.id,
                clearSessionAfter = true,
                clearDownloads = true,
            )
        }
        if (_state.value.session is SessionPhase.SignedIn) refreshApps()
    }

    fun login(phone: String, password: String) {
        if (_state.value.loginBusy) return
        // Persist this barrier before changing the UI. If the process is killed
        // during cleanup, startup treats the old session as signed out and
        // resumes cleanup instead of resurrecting the account.
        val staleSession = repository.markLocalSessionRetiring()
        authAttempt += 1
        val attempt = authAttempt
        val previousAuthJob = authJob
        replaceAccountState(MainUiState(session = SessionPhase.SignedOut, loginBusy = true))
        clearPrivateImageMemoryCache()
        staleSession?.let { stale ->
            scheduleDownloadCleanup(
                userId = stale.user.id,
                clearSessionAfter = true,
                clearDownloads = true,
            )
        }

        authJob = viewModelScope.launch {
            try {
                // ApiClient persists a successful login before returning it. Keep
                // login attempts serialized so an older, uncancellable network
                // response can never overwrite a newer account in secure storage.
                previousAuthJob?.join()
                downloadCleanupJob?.join()

                val session = repository.login(phone, password)
                if (attempt != authAttempt) {
                    if (repository.currentSession()?.accessToken == session.accessToken) {
                        repository.clearLocalSession()
                    }
                    revokeInBackground(session.accessToken)
                    return@launch
                }
                val phase = if (session.user.mustChangePassword) {
                    SessionPhase.PasswordChangeRequired(session)
                } else {
                    SessionPhase.SignedIn(session)
                }
                replaceAccountState(MainUiState(session = phase))
                clearPrivateImageMemoryCache()
                if (phase is SessionPhase.SignedIn) refreshApps()
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (exception: Exception) {
                if (attempt == authAttempt) {
                    _state.value = MainUiState(
                        session = SessionPhase.SignedOut,
                        message = failureMessage(exception),
                        messageIsError = true,
                    )
                }
            }
        }
    }

    fun changeInitialPassword(current: String, replacement: String) {
        val snapshot = _state.value
        val account = currentAccount(readyOnly = false) ?: return
        if (snapshot.session !is SessionPhase.PasswordChangeRequired || snapshot.loginBusy) return
        updateAccount(account) { it.copy(loginBusy = true, message = null, messageIsError = false) }
        accountScope.launch {
            try {
                // The password endpoint clears the local session on success.
                // Stop downloads first so a running worker can still report its
                // cancellation using this account's current credentials.
                val downloadsCleared = clearDownloadsForUser(account.userId)
                repository.changePassword(current, replacement)
                if (isCurrent(account)) {
                    transitionToSignedOut(
                        message = "密码已更新，请使用新密码重新登录",
                        isError = false,
                        departingAccount = account,
                        sessionAlreadyCleared = true,
                        downloadsAlreadyCleared = downloadsCleared,
                    )
                }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (exception: Exception) {
                handleAccountFailure(account, exception) { it.copy(loginBusy = false) }
            }
        }
    }

    fun logout() {
        transitionToSignedOut("已安全退出", isError = false)
    }

    fun refreshApps(search: String = _state.value.search) {
        val account = currentAccount() ?: return
        appsJob?.cancel()
        appsRevision += 1
        val revision = appsRevision
        val changed = _state.value.search != search
        updateAccount(account) {
            it.copy(
                apps = if (changed) emptyList() else it.apps,
                appsLoading = true,
                search = search,
                message = null,
                messageIsError = false,
            )
        }
        appsJob = accountScope.launch {
            try {
                val apps = repository.apps(search)
                if (revision != appsRevision) return@launch
                updateAccount(account) { state ->
                    if (state.search == search) state.copy(apps = apps, appsLoading = false) else state
                }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (exception: Exception) {
                if (revision == appsRevision) {
                    handleAccountFailure(account, exception) { it.copy(appsLoading = false) }
                }
            }
        }
    }

    fun openApp(appId: String) {
        val account = currentAccount() ?: return
        detailJob?.cancel()
        downloadObserver?.cancel()
        detailRevision += 1
        val revision = detailRevision
        updateAccount(account) {
            it.copy(
                detailLoading = true,
                selectedApp = null,
                selectedAppBugCounts = emptyMap(),
                download = DownloadUiState(),
                installation = AppInstallationUiState(),
                message = null,
                messageIsError = false,
            )
        }
        detailJob = accountScope.launch {
            try {
                val appDeferred = async { repository.app(appId) }
                val countsDeferred = async {
                    try {
                        repository.bugCounts(appId)
                    } catch (cancelled: CancellationException) {
                        throw cancelled
                    } catch (_: Exception) {
                        emptyMap()
                    }
                }
                val app = appDeferred.await()
                val counts = countsDeferred.await()
                val installation = inspectAppInstallation(getApplication<Application>().packageManager, app)
                check(app.id == appId) { "服务器返回了错误的应用详情" }
                if (revision != detailRevision) return@launch
                updateAccount(account) {
                    it.copy(
                        selectedApp = app,
                        selectedAppBugCounts = counts,
                        installation = installation,
                        detailLoading = false,
                    )
                }
                app.currentVersion?.let { observeDownload(account, it.id) }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (exception: Exception) {
                if (revision == detailRevision) {
                    handleAccountFailure(account, exception) { it.copy(detailLoading = false) }
                }
            }
        }
    }

    fun clearSelectedApp() {
        val account = currentAccount() ?: return
        detailJob?.cancel()
        downloadObserver?.cancel()
        detailRevision += 1
        updateAccount(account) {
            it.copy(
                selectedApp = null,
                selectedAppBugCounts = emptyMap(),
                detailLoading = false,
                download = DownloadUiState(),
                installation = AppInstallationUiState(),
            )
        }
    }

    fun loadBugs(mine: Boolean = true) {
        loadBugsInternal(mine, _state.value.bugListAppId, _state.value.bugListAppName)
    }

    fun loadAllBugs(mine: Boolean = true) {
        loadBugsInternal(mine, null, null)
    }

    fun loadBugsForApp(appId: String, appName: String) {
        loadBugsInternal(mine = false, appId = appId, appName = appName)
    }

    private fun loadBugsInternal(
        mine: Boolean,
        appId: String?,
        appName: String?,
        clearMessage: Boolean = true,
        requiredAccount: AccountKey? = null,
    ) {
        val account = currentAccount() ?: return
        if (requiredAccount != null && requiredAccount != account) return
        val query = BugQueryKey(mine, appId)
        val queryChanged = _state.value.bugQueryKey() != query
        bugsJob?.cancel()
        bugQueryRevision += 1
        val revision = bugQueryRevision
        updateAccount(account) {
            it.copy(
                myBugs = if (queryChanged) emptyList() else it.myBugs,
                bugTotal = if (queryChanged) 0 else it.bugTotal,
                bugsLoading = true,
                bugsLoadingMore = false,
                bugListMine = mine,
                bugListAppId = appId,
                bugListAppName = appName,
                bugPage = 1,
                message = if (clearMessage) null else it.message,
                messageIsError = if (clearMessage) false else it.messageIsError,
            )
        }
        bugsJob = accountScope.launch {
            try {
                val page = repository.bugs(mine = mine, appId = appId, page = 1)
                if (revision != bugQueryRevision) return@launch
                updateAccount(account) { state ->
                    if (state.bugQueryKey() != query) return@updateAccount state
                    state.copy(
                        myBugs = page.items,
                        bugTotal = page.total,
                        bugPage = page.page,
                        bugsLoading = false,
                    )
                }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (exception: Exception) {
                if (revision == bugQueryRevision && _state.value.bugQueryKey() == query) {
                    handleAccountFailure(account, exception) {
                        if (it.bugQueryKey() == query) it.copy(bugsLoading = false) else it
                    }
                }
            }
        }
    }

    fun loadMoreBugs() {
        val account = currentAccount() ?: return
        val snapshot = _state.value
        if (snapshot.bugsLoading || snapshot.bugsLoadingMore || snapshot.myBugs.size >= snapshot.bugTotal) return
        val query = snapshot.bugQueryKey()
        val revision = bugQueryRevision
        val nextPage = snapshot.bugPage + 1
        bugsJob?.cancel()
        updateAccount(account) { it.copy(bugsLoadingMore = true, message = null, messageIsError = false) }
        bugsJob = accountScope.launch {
            try {
                val page = repository.bugs(
                    mine = query.mine,
                    appId = query.appId,
                    page = nextPage,
                )
                if (revision != bugQueryRevision) return@launch
                updateAccount(account) { state ->
                    if (state.bugQueryKey() != query || state.bugPage != snapshot.bugPage) {
                        return@updateAccount state
                    }
                    state.copy(
                        myBugs = (state.myBugs + page.items).distinctBy(BugReport::id),
                        bugTotal = page.total,
                        bugPage = page.page,
                        bugsLoadingMore = false,
                    )
                }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (exception: Exception) {
                if (revision == bugQueryRevision && _state.value.bugQueryKey() == query) {
                    handleAccountFailure(account, exception) { it.copy(bugsLoadingMore = false) }
                }
            }
        }
    }

    fun loadBug(bugId: String) {
        val account = currentAccount() ?: return
        bugDetailJob?.cancel()
        bugDetailRevision += 1
        val revision = bugDetailRevision
        updateAccount(account) {
            it.copy(
                bugLoading = true,
                selectedBug = null,
                bugEditBusy = false,
                commentBusy = false,
                message = null,
                messageIsError = false,
            )
        }
        bugDetailJob = accountScope.launch {
            try {
                val bug = repository.bug(bugId)
                check(bug.id == bugId) { "服务器返回了错误的 Bug 详情" }
                if (revision != bugDetailRevision) return@launch
                val mutation = activeBugMutations[BugMutationKey(account, bugId)]
                updateAccount(account) {
                    it.copy(
                        selectedBug = bug,
                        bugLoading = mutation?.kind == BugMutationKind.VERIFY,
                        bugEditBusy = mutation?.kind == BugMutationKind.EDIT,
                        commentBusy = mutation?.kind == BugMutationKind.COMMENT,
                    )
                }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (exception: Exception) {
                if (revision == bugDetailRevision) {
                    handleAccountFailure(account, exception) {
                        it.copy(bugLoading = false, bugEditBusy = false, commentBusy = false)
                    }
                }
            }
        }
    }

    fun updateBugText(title: String, description: String, reproductionSteps: String) {
        val account = currentAccount() ?: return
        val original = _state.value.selectedBug ?: return
        val update = normalizedBugTextUpdate(title, description, reproductionSteps)
        val validation = validateBugTextUpdate(update)
        if (validation != null) {
            updateAccount(account) { it.copy(message = validation, messageIsError = true) }
            return
        }
        if (!hasBugTextChanges(original, update)) {
            updateAccount(account) { it.copy(message = "反馈内容没有变化", messageIsError = false) }
            return
        }
        val start = beginBugMutation(
            kind = BugMutationKind.EDIT,
            requireReporter = true,
            requirePending = true,
        ) ?: return
        accountScope.launch {
            try {
                val updated = repository.updateBugText(start.first.bugId, update)
                validateBugTextUpdateResponse(start.third, updated, start.first.account.userId, update)
                if (!isCurrent(start.first.account)) return@launch
                applyBugMutationResult(
                    key = start.first,
                    updated = updated,
                    message = "反馈内容已更新",
                    incrementEditSequence = true,
                )
                reloadCurrentBugQuery(start.first.account)
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (exception: Exception) {
                handleBugMutationFailure(start.first, exception)
            } finally {
                finishBugMutation(start.first, start.second)
            }
        }
    }

    fun addComment(content: String) {
        if (content.isBlank()) return
        val start = beginBugMutation(BugMutationKind.COMMENT) ?: return
        accountScope.launch {
            try {
                val updated = repository.comment(start.first.bugId, content)
                validateBugMutationResult(start.third, updated)
                if (!isCurrent(start.first.account)) return@launch
                applyBugMutationResult(
                    key = start.first,
                    updated = updated,
                    message = "补充信息已发送",
                    incrementCommentSequence = true,
                )
                reloadCurrentBugQuery(start.first.account)
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (exception: Exception) {
                handleBugMutationFailure(start.first, exception)
            } finally {
                finishBugMutation(start.first, start.second)
            }
        }
    }

    fun verifyBug(accepted: Boolean, note: String) {
        val start = beginBugMutation(BugMutationKind.VERIFY, requireReporter = true) ?: return
        accountScope.launch {
            try {
                val updated = repository.verify(start.first.bugId, accepted, note)
                validateBugMutationResult(start.third, updated)
                check(updated.reporterId == start.first.account.userId) { "Bug 验证账户不匹配" }
                if (!isCurrent(start.first.account)) return@launch
                applyBugMutationResult(
                    key = start.first,
                    updated = updated,
                    message = "验证结果已提交",
                )
                reloadCurrentBugQuery(start.first.account)
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (exception: Exception) {
                handleBugMutationFailure(start.first, exception)
            } finally {
                finishBugMutation(start.first, start.second)
            }
        }
    }

    fun submitBug(draft: BugDraft) {
        val account = currentAccount() ?: return
        val snapshot = _state.value
        if (snapshot.submittingBug) return
        val validation = validateDraft(draft)
        if (validation != null) {
            updateAccount(account) { it.copy(message = validation, messageIsError = true) }
            return
        }
        val selectedApp = snapshot.selectedApp
        if (selectedApp?.id != draft.appId || selectedApp.currentVersion?.id != draft.versionId) {
            updateAccount(account) {
                it.copy(message = "应用版本已变化，请返回详情后重新提交", messageIsError = true)
            }
            return
        }
        updateAccount(account) {
            it.copy(submittingBug = true, message = null, messageIsError = false)
        }
        accountScope.launch {
            try {
                val bug = repository.submitBug(draft)
                check(
                    bug.appId == draft.appId &&
                        bug.versionId == draft.versionId &&
                        bug.reporterId == account.userId,
                ) { "服务器返回的 Bug 与当前账户或应用不匹配" }
                if (!isCurrent(account)) return@launch
                bugDraftStore.clear(account.userId, draft.appId, draft.versionId)
                updateAccount(account) {
                    it.copy(
                        submittingBug = false,
                        message = "反馈已提交",
                        messageIsError = false,
                    )
                }
                reloadCurrentBugQuery(account)
                if (isCurrent(account)) _effects.emit(UiEffect.BugSubmitted(bug.id))
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (exception: Exception) {
                handleAccountFailure(account, exception) { it.copy(submittingBug = false) }
            } finally {
                updateAccount(account) { it.copy(submittingBug = false) }
            }
        }
    }

    fun startDownload() {
        val account = currentAccount() ?: return
        val app = _state.value.selectedApp ?: return
        val version = app.currentVersion ?: return
        if (!version.downloadEnabled) {
            updateAccount(account) { it.copy(message = "管理员已暂停此版本下载", messageIsError = true) }
            return
        }
        if (version.minSdk != null && Build.VERSION.SDK_INT < version.minSdk) {
            updateAccount(account) {
                it.copy(message = "此版本需要 Android ${version.minSdk} 或更高版本", messageIsError = true)
            }
            return
        }
        downloadScheduler.enqueue(app, account.userId)
        observeDownload(account, version.id)
    }

    fun cancelDownload() {
        val account = currentAccount() ?: return
        _state.value.selectedApp?.currentVersion?.id?.let {
            downloadScheduler.cancel(account.userId, it)
        }
    }

    fun installDownloadedApk() {
        if (currentAccount() == null) return
        _state.value.download.filePath?.let { _effects.tryEmit(UiEffect.OpenInstaller(it)) }
    }

    fun openInstalledApp() {
        if (currentAccount() == null) return
        _state.value.selectedApp?.packageName?.let { _effects.tryEmit(UiEffect.OpenInstalledApp(it)) }
    }

    fun refreshSelectedAppInstallation() {
        val account = currentAccount() ?: return
        val app = _state.value.selectedApp ?: return
        val installation = inspectAppInstallation(getApplication<Application>().packageManager, app)
        updateAccount(account) { current ->
            if (current.selectedApp?.id == app.id) current.copy(installation = installation) else current
        }
    }

    fun downloadedFileMissing() {
        val account = currentAccount() ?: return
        updateAccount(account) {
            it.copy(
                download = DownloadUiState(phase = DownloadPhase.FAILED, error = "下载文件已被清理，请重新下载"),
            )
        }
    }

    fun dismissMessage() = _state.update { it.copy(message = null, messageIsError = false) }

    private fun observeDownload(account: AccountKey, versionId: String) {
        if (!isCurrent(account)) return
        downloadObserver?.cancel()
        downloadObserver = accountScope.launch {
            downloadScheduler.workManager()
                .getWorkInfosForUniqueWorkFlow(DownloadScheduler.uniqueName(account.userId, versionId))
                .collect { infos ->
                    if (!isCurrent(account)) return@collect
                    val selectedVersionId = _state.value.selectedApp?.currentVersion?.id
                    if (selectedVersionId != versionId) return@collect
                    val info = infos.lastOrNull() ?: return@collect
                    val outputPath = info.outputData.getString(KEY_FILE_PATH)
                    val readyFileOwned = info.state == WorkInfo.State.SUCCEEDED &&
                        downloadScheduler.isOwnedFile(account.userId, outputPath)
                    val phase = when (info.state) {
                        WorkInfo.State.ENQUEUED, WorkInfo.State.BLOCKED -> DownloadPhase.QUEUED
                        WorkInfo.State.RUNNING -> when (info.progress.getString(KEY_PHASE)) {
                            PHASE_PREPARING -> DownloadPhase.PREPARING
                            PHASE_VERIFYING -> DownloadPhase.VERIFYING
                            else -> DownloadPhase.DOWNLOADING
                        }
                        WorkInfo.State.SUCCEEDED -> if (readyFileOwned) DownloadPhase.READY else DownloadPhase.IDLE
                        WorkInfo.State.FAILED, WorkInfo.State.CANCELLED -> DownloadPhase.FAILED
                    }
                    updateAccount(account) {
                        it.copy(
                            download = DownloadUiState(
                                phase = phase,
                                progress = if (phase == DownloadPhase.READY) {
                                    100
                                } else {
                                    info.progress.getInt(KEY_PROGRESS, 0)
                                },
                                filePath = outputPath.takeIf { readyFileOwned },
                                error = info.outputData.getString(KEY_ERROR),
                            ),
                        )
                    }
                }
        }
    }

    private fun beginBugMutation(
        kind: BugMutationKind,
        requireReporter: Boolean = false,
        requirePending: Boolean = false,
    ): Triple<BugMutationKey, ActiveBugMutation, BugReport>? {
        val account = currentAccount() ?: return null
        val snapshot = _state.value
        val bug = snapshot.selectedBug ?: return null
        val key = BugMutationKey(account, bug.id)
        if (activeBugMutations.containsKey(key)) return null
        if (requireReporter && bug.reporterId != account.userId) {
            updateAccount(account) {
                it.copy(
                    message = if (kind == BugMutationKind.EDIT) {
                        "只能编辑自己提交的 Bug"
                    } else {
                        "只能验证自己提交的 Bug"
                    },
                    messageIsError = true,
                )
            }
            return null
        }
        if (requirePending && bug.status != BugState.PENDING) {
            updateAccount(account) {
                it.copy(message = "只有待处理的 Bug 可以编辑", messageIsError = true)
            }
            return null
        }
        val active = ActiveBugMutation(kind)
        activeBugMutations[key] = active
        updateAccount(account) {
            if (it.selectedBug?.id != bug.id) return@updateAccount it
            it.copy(
                bugLoading = kind == BugMutationKind.VERIFY,
                bugEditBusy = kind == BugMutationKind.EDIT,
                commentBusy = kind == BugMutationKind.COMMENT,
                message = null,
                messageIsError = false,
            )
        }
        return Triple(key, active, bug)
    }

    private fun finishBugMutation(key: BugMutationKey, active: ActiveBugMutation) {
        if (activeBugMutations[key] !== active) return
        activeBugMutations.remove(key)
        updateAccount(key.account) {
            if (it.selectedBug?.id != key.bugId) return@updateAccount it
            when (active.kind) {
                BugMutationKind.EDIT -> it.copy(bugEditBusy = false)
                BugMutationKind.COMMENT -> it.copy(commentBusy = false)
                BugMutationKind.VERIFY -> it.copy(bugLoading = false)
            }
        }
    }

    private fun handleBugMutationFailure(key: BugMutationKey, exception: Throwable) {
        if (!isCurrent(key.account)) return
        if ((exception as? ApiException)?.statusCode == 401) {
            handleAccountFailure(key.account, exception)
            return
        }
        if (_state.value.selectedBug?.id == key.bugId) {
            handleAccountFailure(key.account, exception)
        }
    }

    private fun applyBugMutationResult(
        key: BugMutationKey,
        updated: BugReport,
        message: String,
        incrementEditSequence: Boolean = false,
        incrementCommentSequence: Boolean = false,
    ) {
        if (!isCurrent(key.account) || _state.value.selectedBug?.id != key.bugId) return
        bugDetailRevision += 1
        bugDetailJob?.cancel()
        updateAccount(key.account) {
            if (it.selectedBug?.id != key.bugId) return@updateAccount it
            it.copy(
                selectedBug = updated,
                bugEditSubmitSequence = if (incrementEditSequence) {
                    it.bugEditSubmitSequence + 1
                } else {
                    it.bugEditSubmitSequence
                },
                commentSubmitSequence = if (incrementCommentSequence) {
                    it.commentSubmitSequence + 1
                } else {
                    it.commentSubmitSequence
                },
                message = message,
                messageIsError = false,
            )
        }
    }

    private fun validateBugMutationResult(original: BugReport, updated: BugReport) {
        check(
            updated.id == original.id &&
                updated.appId == original.appId &&
                updated.versionId == original.versionId,
        ) { "服务器返回的 Bug 与当前操作不匹配" }
    }

    private fun reloadCurrentBugQuery(account: AccountKey) {
        if (!isCurrent(account)) return
        val snapshot = _state.value
        loadBugsInternal(
            mine = snapshot.bugListMine,
            appId = snapshot.bugListAppId,
            appName = snapshot.bugListAppName,
            clearMessage = false,
            requiredAccount = account,
        )
    }

    private fun currentAccount(readyOnly: Boolean = true): AccountKey? {
        val phase = _state.value.session
        val userId = when (phase) {
            is SessionPhase.SignedIn -> phase.session.user.id
            is SessionPhase.PasswordChangeRequired -> {
                if (readyOnly) return null
                phase.session.user.id
            }
            SessionPhase.SignedOut -> return null
        }
        return AccountKey(accountGeneration, userId)
    }

    private fun isCurrent(account: AccountKey): Boolean =
        account.generation == accountGeneration && sessionUserId(_state.value.session) == account.userId

    private inline fun updateAccount(account: AccountKey, transform: (MainUiState) -> MainUiState) {
        if (!isCurrent(account)) return
        _state.update { current ->
            if (account.generation == accountGeneration && sessionUserId(current.session) == account.userId) {
                transform(current)
            } else {
                current
            }
        }
    }

    private fun replaceAccountState(newState: MainUiState) {
        accountGeneration += 1
        accountRootJob.cancel()
        accountRootJob = SupervisorJob(viewModelScope.coroutineContext[Job])
        accountScope = CoroutineScope(viewModelScope.coroutineContext + accountRootJob)
        downloadObserver = null
        appsJob = null
        detailJob = null
        bugsJob = null
        bugDetailJob = null
        appsRevision = 0L
        detailRevision = 0L
        bugQueryRevision = 0L
        bugDetailRevision = 0L
        activeBugMutations.clear()
        _state.value = newState
    }

    private fun transitionToSignedOut(
        message: String,
        isError: Boolean,
        departingAccount: AccountKey? = currentAccount(readyOnly = false),
        sessionAlreadyCleared: Boolean = false,
        downloadsAlreadyCleared: Boolean = false,
    ) {
        val retiringSession = if (sessionAlreadyCleared) {
            null
        } else {
            repository.markLocalSessionRetiring()
        }
        val userId = departingAccount?.userId ?: retiringSession?.user?.id
        authAttempt += 1
        replaceAccountState(
            MainUiState(
                session = SessionPhase.SignedOut,
                message = message,
                messageIsError = isError,
            ),
        )
        clearPrivateImageMemoryCache()
        if (!sessionAlreadyCleared || !downloadsAlreadyCleared) {
            scheduleDownloadCleanup(
                userId = userId,
                clearSessionAfter = !sessionAlreadyCleared,
                clearDownloads = !downloadsAlreadyCleared,
            )
        }
    }

    private fun scheduleDownloadCleanup(
        userId: String?,
        clearSessionAfter: Boolean,
        clearDownloads: Boolean,
    ) {
        val previous = downloadCleanupJob
        downloadCleanupJob = viewModelScope.launch {
            previous?.join()
            if (clearDownloads && userId != null) {
                clearDownloadsForUser(userId)
            }
            if (clearSessionAfter) {
                val accessToken = repository.clearLocalSession()
                revokeInBackground(accessToken)
            }
        }
    }

    private suspend fun clearDownloadsForUser(userId: String): Boolean = try {
        downloadScheduler.clearForUser(userId)
        true
    } catch (cancelled: CancellationException) {
        throw cancelled
    } catch (_: Exception) {
        false
    }

    private fun revokeInBackground(accessToken: String?) {
        if (accessToken.isNullOrBlank()) return
        viewModelScope.launch { runCatching { repository.revokeSession(accessToken) } }
    }

    private fun handleAccountFailure(
        account: AccountKey,
        exception: Throwable,
        clearBusy: (MainUiState) -> MainUiState = { it },
    ) {
        if (!isCurrent(account)) return
        val apiException = exception as? ApiException
        if (apiException?.statusCode == 401) {
            transitionToSignedOut(apiException.message, isError = true, departingAccount = account)
            return
        }
        updateAccount(account) {
            clearBusy(it).copy(
                message = failureMessage(exception),
                messageIsError = true,
            )
        }
    }

    private fun MainUiState.bugQueryKey(): BugQueryKey = BugQueryKey(bugListMine, bugListAppId)

    private fun sessionUserId(phase: SessionPhase): String? = when (phase) {
        is SessionPhase.SignedIn -> phase.session.user.id
        is SessionPhase.PasswordChangeRequired -> phase.session.user.id
        SessionPhase.SignedOut -> null
    }

    private fun validateDraft(draft: BugDraft): String? = when {
        draft.title.trim().length !in 2..120 -> "Bug 标题需要 2–120 个字符"
        draft.description.trim().length !in 2..10_000 -> "问题描述需要 2–10000 个字符"
        draft.reproductionSteps.trim().length > 5000 -> "复现步骤不能超过 5000 个字符"
        draft.screenshots.size > 5 -> "最多选择 5 张截图"
        draft.visibility !in setOf("group", "private") -> "请选择反馈可见范围"
        else -> null
    }

    private fun failureMessage(exception: Throwable): String = userFacingFailureMessage(exception)
}

internal fun userFacingFailureMessage(exception: Throwable): String = when (exception) {
    is ApiException -> exception.message
    is IOException -> "网络连接失败，请检查网络后重试"
    else -> "操作未完成，请稍后重试"
}
