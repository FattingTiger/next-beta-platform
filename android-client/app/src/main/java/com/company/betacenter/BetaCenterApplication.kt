package com.company.betacenter

import android.app.Application
import com.company.betacenter.data.ApiClient
import com.company.betacenter.data.BetaRepository
import com.company.betacenter.data.BugDraftStore
import com.company.betacenter.security.SecureSessionStore
import com.company.betacenter.update.ClientUpdateManager

class BetaCenterApplication : Application() {
    val container: AppContainer by lazy(LazyThreadSafetyMode.SYNCHRONIZED) { AppContainer(this) }

    override fun onCreate() {
        super.onCreate()
        container.clientUpdateManager.scheduleWeeklyChecks()
    }
}

class AppContainer(application: Application) {
    private val sessionStore = SecureSessionStore(application)
    val api = ApiClient(sessionStore)
    val repository = BetaRepository(application, api)
    val bugDraftStore = BugDraftStore(application)
    val clientUpdateManager = ClientUpdateManager(application)
}
