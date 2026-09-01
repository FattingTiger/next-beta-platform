package com.company.betacenter.data

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class JsonParsersTest {
    @Test
    fun `tester app detail reads current version even when versions history is empty`() {
        val json = JSONObject(
            """
            {
              "id":"app-1",
              "name":"巡检助手",
              "package_name":"com.company.inspection",
              "short_description":"门店巡检内测版",
              "description":"用于巡检流程测试",
              "status":"published",
              "icon_url":"/api/v1/files/apps/app-1/icon",
              "current_version":${versionJson()},
              "group_ids":["g-1"],
              "screenshots":[
                {"id":"shot-2","position":2,"content_type":"image/webp","url":"/shot-2"},
                {"id":"shot-1","position":1,"content_type":"image/webp","url":"/shot-1"}
              ],
              "versions":[],
              "created_at":"2026-08-29T00:00:00Z",
              "updated_at":"2026-08-29T01:00:00Z"
            }
            """.trimIndent(),
        )

        val app = parseAppDetails(json)

        assertEquals("version-1", app.currentVersion?.id)
        assertEquals("2.4.0", app.currentVersion?.versionName)
        assertEquals(listOf("shot-1", "shot-2"), app.screenshots.map(AppScreenshot::id))
    }

    @Test
    fun `group visible bug tolerates deliberately omitted sensitive fields`() {
        val json = JSONObject(
            """
            {
              "id":"bug-1",
              "reference":"BT-ABC12345",
              "app_id":"app-1",
              "app_name":"巡检助手",
              "version_id":"version-1",
              "version_name":"2.4.0",
              "title":"提交后页面空白",
              "status":"in_progress",
              "visibility":"group",
              "resolution_note":"",
              "attachments":[],
              "comments":[],
              "transitions":[],
              "created_at":"2026-08-29T00:00:00Z",
              "updated_at":"2026-08-29T01:00:00Z"
            }
            """.trimIndent(),
        )

        val bug = parseBug(json)

        assertNull(bug.reporterId)
        assertNull(bug.description)
        assertEquals(BugState.IN_PROGRESS, bug.status)
        assertEquals(emptyList<BugAttachment>(), bug.attachments)
    }

    @Test
    fun `stored session round trip preserves rotated tokens and user`() {
        val session = AuthSession(
            accessToken = "new-access-token",
            refreshToken = "new-refresh-token",
            expiresAtEpochMillis = 1_800_000_000_000,
            user = UserProfile(
                id = "user-1",
                displayName = "测试员工",
                phone = "+8613800000000",
                role = "tester",
                mustChangePassword = false,
                groupIds = listOf("group-1"),
            ),
        )

        assertEquals(session, storedSessionFromJson(sessionToJson(session)))
    }

    @Test
    fun `app list accepts an empty catalog`() {
        assertEquals(emptyList<AppCard>(), parseApps(JSONArray()))
    }

    @Test
    fun `bug page keeps server pagination metadata`() {
        val bug = JSONObject(
            """
            {
              "id":"bug-1","reference":"BT-ABC12345","app_id":"app-1","app_name":"巡检助手",
              "version_id":"version-1","version_name":"2.4.0","title":"闪退","status":"pending",
              "visibility":"private","resolution_note":"","attachments":[],"comments":[],"transitions":[],
              "created_at":"2026-08-29T00:00:00Z","updated_at":"2026-08-29T01:00:00Z"
            }
            """.trimIndent(),
        )
        val page = parseBugPage(
            JSONObject().apply {
                put("items", JSONArray().put(bug))
                put("total", 73)
                put("page", 2)
                put("page_size", 50)
            },
        )

        assertEquals(73, page.total)
        assertEquals(2, page.page)
        assertEquals(50, page.pageSize)
        assertEquals("bug-1", page.items.single().id)
    }

    @Test
    fun `unknown future bug state degrades safely`() {
        assertEquals(BugState.UNKNOWN, BugState.fromWire("awaiting_release"))
    }

    @Test
    fun `download ticket preserves integrity metadata and relative URL`() {
        val ticket = parseDownloadTicket(
            JSONObject(
                """
                {
                  "download_id":"download-1","client_request_id":"request-1",
                  "url":"/api/v1/downloads/download-1/file","file_size":4096,
                  "sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                  "filename":"qa-playground-1.0.0.apk"
                }
                """.trimIndent(),
            ),
        )

        assertEquals("request-1", ticket.clientRequestId)
        assertEquals(4096, ticket.fileSize)
        assertEquals("/api/v1/downloads/download-1/file", ticket.url)
    }

    @Test
    fun `user without groups parses as an empty assignment`() {
        val user = parseUser(
            JSONObject(
                """
                {
                  "id":"user-1","display_name":"测试员工","phone":"+8613800000000",
                  "role":"tester","must_change_password":false
                }
                """.trimIndent(),
            ),
        )

        assertEquals(emptyList<String>(), user.groupIds)
    }

    private fun versionJson(): String =
        """
        {
          "id":"version-1",
          "version_name":"2.4.0",
          "version_code":240,
          "min_sdk":26,
          "target_sdk":35,
          "file_size":8388608,
          "sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
          "signing_cert_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
          "release_notes":"修复离线同步",
          "status":"published",
          "download_enabled":true,
          "created_at":"2026-08-29T00:00:00Z",
          "published_at":"2026-08-29T00:30:00Z"
        }
        """.trimIndent()
}
