package com.company.betacenter.data

import android.content.Context
import android.net.Uri
import androidx.core.content.edit
import androidx.core.net.toUri
import org.json.JSONArray
import org.json.JSONObject

class BugDraftStore(context: Context) {
    private val preferences = context.getSharedPreferences("bug_drafts", Context.MODE_PRIVATE)

    fun load(userId: String, appId: String, versionId: String): BugDraft? {
        val raw = preferences.getString(key(userId, appId, versionId), null) ?: return null
        return runCatching {
            val json = JSONObject(raw)
            BugDraft(
                appId = appId,
                versionId = versionId,
                title = json.optString("title"),
                description = json.optString("description"),
                reproductionSteps = json.optString("reproduction_steps"),
                visibility = json.optString("visibility", "group"),
                screenshots = buildList {
                    val values = json.optJSONArray("screenshots") ?: JSONArray()
                    for (index in 0 until values.length()) add(values.getString(index).toUri())
                },
            )
        }.getOrNull()
    }

    fun save(userId: String, draft: BugDraft) {
        val json = JSONObject()
            .put("title", draft.title)
            .put("description", draft.description)
            .put("reproduction_steps", draft.reproductionSteps)
            .put("visibility", draft.visibility)
            .put("screenshots", JSONArray(draft.screenshots.map(Uri::toString)))
        preferences.edit { putString(key(userId, draft.appId, draft.versionId), json.toString()) }
    }

    fun clear(userId: String, appId: String, versionId: String) {
        preferences.edit { remove(key(userId, appId, versionId)) }
    }

    private fun key(userId: String, appId: String, versionId: String): String =
        listOf(userId, appId, versionId).joinToString("|")
}
