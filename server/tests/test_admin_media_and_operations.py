from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from conftest import DEFAULT_PASSWORD, ApiContext, FakeApkMetadata, PublishedApp
from sqlalchemy import select

from beta_center.models import AppVersion, AuditLog, DownloadRecord

SERVER_ROOT = Path(__file__).resolve().parents[1]


def error_code(response: object) -> str:
    return response.json()["error"]["code"]  # type: ignore[attr-defined,no-any-return]


def test_permanent_app_delete_requires_archive_and_password_and_removes_apk(
    context: ApiContext,
    published_app: PublishedApp,
) -> None:
    with context.runtime.database.session() as db:
        version = db.get(AppVersion, published_app.version_id)
        assert version is not None
        apk_path = context.runtime.storage.path_for(version.file_storage_key)
    assert apk_path.is_file()

    active = context.client.request(
        "DELETE",
        f"/api/v1/admin/apps/{published_app.app_id}",
        headers=published_app.admin_auth.bearer,
        json={"current_password": DEFAULT_PASSWORD},
    )
    assert active.status_code == 409
    assert error_code(active) == "app_must_be_archived"

    archived = context.client.patch(
        f"/api/v1/admin/apps/{published_app.app_id}",
        headers=published_app.admin_auth.bearer,
        json={"status": "archived"},
    )
    assert archived.status_code == 200

    wrong = context.client.request(
        "DELETE",
        f"/api/v1/admin/apps/{published_app.app_id}",
        headers=published_app.admin_auth.bearer,
        json={"current_password": "Wrong-Password-1!"},
    )
    assert wrong.status_code == 400
    assert error_code(wrong) == "current_password_invalid"
    assert apk_path.is_file()

    deleted = context.client.request(
        "DELETE",
        f"/api/v1/admin/apps/{published_app.app_id}",
        headers=published_app.admin_auth.bearer,
        json={"current_password": DEFAULT_PASSWORD},
    )
    assert deleted.status_code == 204, deleted.text
    assert not apk_path.exists()
    assert (
        context.client.get(
            f"/api/v1/admin/apps/{published_app.app_id}",
            headers=published_app.admin_auth.bearer,
        ).status_code
        == 404
    )
    with context.runtime.database.session() as db:
        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "admin.app.permanent_delete",
                AuditLog.entity_id == published_app.app_id,
                AuditLog.outcome == "success",
            )
        )
        assert audit is not None


def test_permanent_group_user_and_bug_delete_only_after_recoverable_delete(
    context: ApiContext,
    published_app: PublishedApp,
) -> None:
    bug = context.client.post(
        "/api/v1/bugs",
        headers=published_app.alice_auth.bearer,
        data={
            "app_id": published_app.app_id,
            "version_id": published_app.version_id,
            "title": "待永久删除的问题",
            "description": "用于验证永久删除保护流程",
        },
    )
    assert bug.status_code == 201
    bug_id = bug.json()["id"]
    user_bug = context.client.post(
        "/api/v1/bugs",
        headers=published_app.bob_auth.bearer,
        data={
            "app_id": published_app.app_id,
            "version_id": published_app.version_id,
            "title": "随用户永久删除的问题",
            "description": "验证用户反馈会随账号永久删除",
        },
    )
    assert user_bug.status_code == 201
    user_bug_id = user_bug.json()["id"]

    for endpoint in (
        f"/api/v1/admin/groups/{published_app.group_id}",
        f"/api/v1/admin/users/{context.bob.id}",
        f"/api/v1/admin/bugs/{bug_id}",
    ):
        premature = context.client.request(
            "DELETE",
            endpoint,
            headers=published_app.admin_auth.bearer,
            json={"current_password": DEFAULT_PASSWORD},
        )
        assert premature.status_code == 409

    assert (
        context.client.patch(
            f"/api/v1/admin/groups/{published_app.group_id}",
            headers=published_app.admin_auth.bearer,
            json={"is_active": False},
        ).status_code
        == 200
    )
    assert (
        context.client.patch(
            f"/api/v1/admin/users/{context.bob.id}",
            headers=published_app.admin_auth.bearer,
            json={"is_active": False},
        ).status_code
        == 200
    )
    assert (
        context.client.patch(
            f"/api/v1/admin/bugs/{bug_id}/deletion",
            headers=published_app.admin_auth.bearer,
            json={"deleted": True},
        ).status_code
        == 200
    )

    for endpoint in (
        f"/api/v1/admin/bugs/{bug_id}",
        f"/api/v1/admin/groups/{published_app.group_id}",
        f"/api/v1/admin/users/{context.bob.id}",
    ):
        deleted = context.client.request(
            "DELETE",
            endpoint,
            headers=published_app.admin_auth.bearer,
            json={"current_password": DEFAULT_PASSWORD},
        )
        assert deleted.status_code == 204, deleted.text

    assert (
        context.client.get(
            f"/api/v1/admin/bugs/{bug_id}", headers=published_app.admin_auth.bearer
        ).status_code
        == 404
    )
    assert (
        context.client.get(
            f"/api/v1/admin/groups/{published_app.group_id}", headers=published_app.admin_auth.bearer
        ).status_code
        == 404
    )
    assert (
        context.client.get(
            f"/api/v1/admin/users/{context.bob.id}", headers=published_app.admin_auth.bearer
        ).status_code
        == 404
    )
    assert (
        context.client.get(
            f"/api/v1/admin/bugs/{user_bug_id}", headers=published_app.admin_auth.bearer
        ).status_code
        == 404
    )


def test_icon_and_screenshot_media_are_normalized_ordered_and_authorized(
    context: ApiContext,
    published_app: PublishedApp,
    png_bytes: bytes,
) -> None:
    icon = context.client.post(
        f"/api/v1/admin/apps/{published_app.app_id}/icon",
        headers=published_app.admin_auth.bearer,
        files={"file": ("icon.png", png_bytes, "image/png")},
    )
    assert icon.status_code == 200, icon.text
    icon_url = icon.json()["icon_url"]
    assert icon_url == f"/api/v1/files/apps/{published_app.app_id}/icon"

    first = context.client.post(
        f"/api/v1/admin/apps/{published_app.app_id}/screenshots",
        headers=published_app.admin_auth.bearer,
        data={"position": "0"},
        files={"file": ("first.png", png_bytes, "image/png")},
    )
    assert first.status_code == 200, first.text
    assert [shot["position"] for shot in first.json()["screenshots"]] == [0]
    first_id = first.json()["screenshots"][0]["id"]

    second = context.client.post(
        f"/api/v1/admin/apps/{published_app.app_id}/screenshots",
        headers=published_app.admin_auth.bearer,
        data={"position": "0"},
        files={"file": ("second.png", png_bytes, "image/png")},
    )
    assert second.status_code == 200, second.text
    assert [shot["position"] for shot in second.json()["screenshots"]] == [0, 1]
    assert second.json()["screenshots"][1]["id"] == first_id

    alice_icon = context.client.get(icon_url, headers=published_app.alice_auth.bearer)
    assert alice_icon.status_code == 200
    assert alice_icon.headers["content-type"] == "image/webp"
    assert alice_icon.content.startswith(b"RIFF")
    screenshot_url = second.json()["screenshots"][0]["url"]
    assert context.client.get(screenshot_url, headers=published_app.alice_auth.bearer).status_code == 200

    outsider = context.login(context.outsider)
    assert context.client.get(icon_url, headers=outsider.bearer).status_code == 404
    assert context.client.get(screenshot_url, headers=outsider.bearer).status_code == 404
    context.client.cookies.clear()
    assert context.client.get(icon_url).status_code == 401

    delete = context.client.delete(
        f"/api/v1/admin/apps/{published_app.app_id}/screenshots/{first_id}",
        headers=published_app.admin_auth.bearer,
    )
    assert delete.status_code == 204
    detail = context.client.get(
        f"/api/v1/admin/apps/{published_app.app_id}",
        headers=published_app.admin_auth.bearer,
    )
    assert detail.status_code == 200
    assert [shot["position"] for shot in detail.json()["screenshots"]] == [0]
    assert (
        context.client.get(
            f"/api/v1/files/apps/{published_app.app_id}/screenshots/{first_id}",
            headers=published_app.admin_auth.bearer,
        ).status_code
        == 404
    )


def test_invalid_media_is_rejected_without_replacing_existing_icon(
    context: ApiContext,
    published_app: PublishedApp,
    png_bytes: bytes,
) -> None:
    valid = context.client.post(
        f"/api/v1/admin/apps/{published_app.app_id}/icon",
        headers=published_app.admin_auth.bearer,
        files={"file": ("icon.png", png_bytes, "image/png")},
    )
    assert valid.status_code == 200
    icon_url = valid.json()["icon_url"]
    original = context.client.get(icon_url, headers=published_app.alice_auth.bearer).content

    invalid = context.client.post(
        f"/api/v1/admin/apps/{published_app.app_id}/icon",
        headers=published_app.admin_auth.bearer,
        files={"file": ("fake.png", b"not-an-image", "image/png")},
    )
    assert invalid.status_code == 422
    assert error_code(invalid) == "invalid_upload"
    assert context.client.get(icon_url, headers=published_app.alice_auth.bearer).content == original


def test_draft_version_explicit_publish_and_disable_lifecycle(context: ApiContext) -> None:
    admin = context.login(context.admin)
    group = context.create_group(admin, member_ids=[context.alice.id])
    app = context.create_app(admin, group_ids=[str(group["id"])])

    cannot_publish_empty = context.client.patch(
        f"/api/v1/admin/apps/{app['id']}",
        headers=admin.bearer,
        json={"status": "published"},
    )
    assert cannot_publish_empty.status_code == 409
    assert error_code(cannot_publish_empty) == "publish_version_required"

    draft = context.upload_version(
        admin,
        str(app["id"]),
        FakeApkMetadata(version_code=10, version_name="1.0-rc"),
        publish=False,
    )
    assert draft["status"] == "draft"
    assert draft["download_enabled"] is False
    assert context.client.get("/api/v1/apps", headers=context.login(context.alice).bearer).json() == []

    context.inspector.queue(FakeApkMetadata(version_code=10, version_name="1.0-rc"))
    published = context.client.post(
        f"/api/v1/admin/apps/{app['id']}/versions/{draft['id']}/publish",
        headers=admin.bearer,
        json={"release_notes": "首个正式内测版本"},
    )
    assert published.status_code == 200
    assert published.json()["status"] == "published"
    assert published.json()["release_notes"] == "首个正式内测版本"

    disabled = context.client.post(
        f"/api/v1/admin/apps/{app['id']}/versions/{draft['id']}/disable",
        headers=admin.bearer,
    )
    assert disabled.status_code == 200
    assert disabled.json()["status"] == "disabled"
    assert disabled.json()["download_enabled"] is False
    admin_detail = context.client.get(f"/api/v1/admin/apps/{app['id']}", headers=admin.bearer)
    assert admin_detail.status_code == 200
    assert admin_detail.json()["status"] == "draft"
    assert admin_detail.json()["current_version"] is None


def test_admin_dashboard_download_and_audit_queries_reconcile(
    context: ApiContext,
    published_app: PublishedApp,
) -> None:
    ticket_response = context.client.post(
        "/api/v1/downloads",
        headers=published_app.alice_auth.bearer,
        json={"version_id": published_app.version_id, "device_model": "Pixel 9"},
    )
    assert ticket_response.status_code == 201
    ticket = ticket_response.json()
    assert (
        context.client.post(
            f"/api/v1/downloads/{ticket['download_id']}/complete",
            headers=published_app.alice_auth.bearer,
            json={"sha256": ticket["sha256"], "bytes_received": ticket["file_size"]},
        ).status_code
        == 204
    )

    dashboard = context.client.get(
        "/api/v1/admin/dashboard",
        headers=published_app.admin_auth.bearer,
    )
    assert dashboard.status_code == 200
    assert dashboard.json() == {
        "active_users": 5,
        "active_apps": 1,
        "published_versions": 1,
        "open_bugs": 0,
        "downloads_started_7d": 1,
        "downloads_completed_7d": 1,
    }

    downloads = context.client.get(
        "/api/v1/admin/downloads",
        headers=published_app.admin_auth.bearer,
        params={
            "user_id": context.alice.id,
            "app_id": published_app.app_id,
            "version_id": published_app.version_id,
            "status": "completed",
            "page_size": 1,
        },
    )
    assert downloads.status_code == 200
    assert downloads.json()["total"] == 1
    assert downloads.json()["items"][0]["id"] == ticket["download_id"]
    assert downloads.json()["items"][0]["status"] == "completed"

    audits = context.client.get(
        "/api/v1/admin/audit-logs",
        headers=published_app.admin_auth.bearer,
        params={"action": "admin.version.upload", "actor_id": context.admin.id},
    )
    assert audits.status_code == 200
    assert audits.json()["total"] == 1
    entry = audits.json()["items"][0]
    assert entry["actor_name"] == context.admin.display_name
    assert entry["entity_type"] == "app_version"
    assert "password" not in str(entry["details"]).lower()


def test_admin_downloads_filter_by_inclusive_timezone_safe_created_range(
    context: ApiContext,
    published_app: PublishedApp,
) -> None:
    ticket_response = context.client.post(
        "/api/v1/downloads",
        headers=published_app.alice_auth.bearer,
        json={"version_id": published_app.version_id},
    )
    assert ticket_response.status_code == 201
    download_id = ticket_response.json()["download_id"]
    with context.runtime.database.session() as db:
        created_at = db.scalar(select(DownloadRecord.created_at).where(DownloadRecord.id == download_id))
    assert created_at is not None
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    same_in_china = created_at.astimezone(timezone(timedelta(hours=8))).isoformat()

    exact = context.client.get(
        "/api/v1/admin/downloads",
        headers=published_app.admin_auth.bearer,
        params={
            "version_id": published_app.version_id,
            "created_from": same_in_china,
            "created_to": same_in_china,
        },
    )
    assert exact.status_code == 200
    assert exact.json()["total"] == 1
    assert exact.json()["items"][0]["id"] == download_id

    after_record = context.client.get(
        "/api/v1/admin/downloads",
        headers=published_app.admin_auth.bearer,
        params={"created_from": (created_at + timedelta(microseconds=1)).isoformat()},
    )
    assert after_record.status_code == 200
    assert after_record.json()["total"] == 0


def test_admin_download_time_filter_rejects_ambiguous_or_reversed_ranges(
    context: ApiContext,
) -> None:
    admin = context.login(context.admin)
    start = datetime(2026, 8, 29, 12, tzinfo=UTC)
    reversed_range = context.client.get(
        "/api/v1/admin/downloads",
        headers=admin.bearer,
        params={
            "created_from": start.isoformat(),
            "created_to": (start - timedelta(seconds=1)).isoformat(),
        },
    )
    assert reversed_range.status_code == 422
    assert error_code(reversed_range) == "invalid_time_range"

    ambiguous = context.client.get(
        "/api/v1/admin/downloads",
        headers=admin.bearer,
        params={"created_from": start.replace(tzinfo=None).isoformat()},
    )
    assert ambiguous.status_code == 422
    assert error_code(ambiguous) == "timezone_required"


def test_admin_download_web_filter_contract_keeps_version_and_time_across_pages() -> None:
    script = (SERVER_ROOT / "src" / "beta_center" / "web" / "admin.js").read_text(encoding="utf-8")
    renderer_start = script.index("async function renderDownloads")
    renderer_end = script.index("\nfunction shortId", renderer_start)
    renderer = script[renderer_start:renderer_end]

    filter_state = (
        'downloads: { status: "", user_id: "", app_id: "", version_id: "", '
        'created_from: "", created_to: "", page: 1 }'
    )
    assert filter_state in script
    assert '["status", "user_id", "app_id", "version_id"]' in renderer
    assert '["created_from", "created_to"]' in renderer
    assert renderer.count('type: "datetime-local"') == 2
    assert 'app.addEventListener("change", async () =>' in renderer
    assert 'setDownloadVersionOptions(version, detail.versions || [], "", true)' in renderer
    assert 'pagination(pageData, (page) => { filters.page = page; renderRoute("downloads"); })' in renderer
    assert 'version_id: "", created_from: "", created_to: "", page: 1' in renderer


def test_admin_list_rows_expose_recoverable_lifecycle_actions() -> None:
    script = (SERVER_ROOT / "src" / "beta_center" / "web" / "admin.js").read_text(encoding="utf-8")

    apps = script[script.index("async function renderApps") : script.index("async function openAppForm")]
    groups = script[
        script.index("async function renderGroups") : script.index("async function openGroupForm")
    ]
    users = script[script.index("async function renderUsers") : script.index("async function openUserForm")]
    bugs = script[script.index("async function renderBugs") : script.index("async function openBugDetail")]

    assert 'app.status === "archived" ? "恢复" : "归档"' in apps
    assert 'app.status === "archived" ? button("永久删除"' in apps
    assert 'group.is_active ? "删除" : "恢复"' in groups
    assert '!group.is_active ? button("永久删除"' in groups
    assert 'user.is_active ? "删除" : "恢复"' in users
    assert '!user.is_active ? button("永久删除"' in users
    assert 'bug.deleted_at ? "恢复" : "删除"' in bugs
    assert 'bug.deleted_at ? button("永久删除"' in bugs


def test_admin_lists_expose_checkbox_bulk_management_and_password_confirmation() -> None:
    script = (SERVER_ROOT / "src" / "beta_center" / "web" / "admin.js").read_text(encoding="utf-8")
    stylesheet = (SERVER_ROOT / "src" / "beta_center" / "web" / "admin.css").read_text(encoding="utf-8")

    for route in ("apps", "groups", "users", "bugs"):
        assert f'bulk.enabled ? bulkRowCheckbox("{route}"' in script
        assert f'bulkHeaderCheckbox("{route}"' in script
        assert f'bulkSelectionBar("{route}"' in script
        assert f'toggleBulkMode("{route}")' in script

    assert "async function runBulkLifecycle" in script
    assert "function openBulkPermanentDelete" in script
    assert 'title: "确认批量永久删除"' in script
    assert "json: { current_password: password.value }" in script
    assert "retryReauth: false" in script
    assert "item.id !== state.user?.id" in script
    assert ".bulk-action-bar" in stylesheet
    assert ".bulk-checkbox" in stylesheet
    assert ".data-table tbody tr.is-selected" in stylesheet


def test_admin_dashboard_uses_concrete_testing_and_download_copy() -> None:
    script = (SERVER_ROOT / "src" / "beta_center" / "web" / "admin.js").read_text(encoding="utf-8")
    dashboard = script[script.index("async function renderDashboard") : script.index("function lensFact")]

    assert '`${summary.active_apps} 个应用正在内测`' in dashboard
    assert '当前还没有已发布版本。' in dashboard
    assert '个已发布版本面向测试用户开放。' in dashboard
    assert '下载完成仅代表文件校验通过，不代表安装成功。' in dashboard
    assert '当前发布面保持清晰' not in dashboard
    assert '问题等待闭环' not in dashboard


def test_admin_web_uses_next_stitch_shell_and_bug_summary_contract() -> None:
    web_root = SERVER_ROOT / "src" / "beta_center" / "web"
    shell = (web_root / "admin.html").read_text(encoding="utf-8")
    script = (web_root / "admin.js").read_text(encoding="utf-8")
    stylesheet = (web_root / "admin.css").read_text(encoding="utf-8")
    bugs = script[script.index("async function renderBugs") : script.index("async function openBugDetail")]

    assert "NEXT Beta · 管理后台" in shell
    assert 'id="sidebar-new-app"' in shell
    assert shell.count("/admin/assets/assets/next-icon-128.png") == 3
    assert "Stitch MCP reference implementation" in stylesheet
    for selector in (
        ".sidebar-primary-action",
        ".dashboard-lens",
        ".testing-app-grid",
        ".bug-metric-grid",
        ".dialog--detail[open]",
    ):
        assert selector in stylesheet

    for status in ("pending", "in_progress", "verifying", "closed"):
        assert f'/admin/bugs?status={status}&deleted=false&page_size=1' in bugs
    assert 'className: "metric-grid bug-metric-grid"' in bugs

    for asset in ("next-icon-128.png", "next-icon-48.png"):
        assert (web_root / "assets" / asset).is_file()


def test_admin_lists_filter_and_paginate_users_groups_and_apps(
    context: ApiContext,
    published_app: PublishedApp,
) -> None:
    users = context.client.get(
        "/api/v1/admin/users",
        headers=published_app.admin_auth.bearer,
        params={"search": "测试用户", "role": "tester", "group_id": published_app.group_id},
    )
    assert users.status_code == 200
    assert users.json()["total"] == 2
    assert {item["id"] for item in users.json()["items"]} == {context.alice.id, context.bob.id}

    groups = context.client.get(
        "/api/v1/admin/groups",
        headers=published_app.admin_auth.bearer,
        params={"search": "核心", "active": True, "page": 1, "page_size": 1},
    )
    assert groups.status_code == 200
    assert groups.json()["total"] == 1
    assert groups.json()["items"][0]["id"] == published_app.group_id

    apps = context.client.get(
        "/api/v1/admin/apps",
        headers=published_app.admin_auth.bearer,
        params={"search": "com.example", "status": "published", "group_id": published_app.group_id},
    )
    assert apps.status_code == 200
    assert apps.json()["total"] == 1
    assert apps.json()["items"][0]["id"] == published_app.app_id


def test_admin_can_change_bug_visibility_and_query_each_resolution(
    context: ApiContext,
    published_app: PublishedApp,
) -> None:
    created = context.client.post(
        "/api/v1/bugs",
        headers=published_app.alice_auth.bearer,
        data={
            "app_id": published_app.app_id,
            "version_id": published_app.version_id,
            "title": "后台处理示例",
            "description": "用于覆盖管理员筛选、可见性和关闭结论。",
        },
    )
    assert created.status_code == 201
    bug_id = created.json()["id"]

    visibility = context.client.patch(
        f"/api/v1/admin/bugs/{bug_id}/visibility",
        headers=published_app.admin_auth.bearer,
        json={"visibility": "private"},
    )
    assert visibility.status_code == 200
    assert visibility.json()["visibility"] == "private"
    assert (
        context.client.get(f"/api/v1/bugs/{bug_id}", headers=published_app.bob_auth.bearer).status_code == 404
    )

    closed = context.client.patch(
        f"/api/v1/admin/bugs/{bug_id}/status",
        headers=published_app.admin_auth.bearer,
        json={"status": "closed", "resolution": "not_a_bug", "note": "符合当前产品定义"},
    )
    assert closed.status_code == 200
    assert closed.json()["resolution"] == "not_a_bug"
    assert closed.json()["resolution_note"] == "符合当前产品定义"

    filtered = context.client.get(
        "/api/v1/admin/bugs",
        headers=published_app.admin_auth.bearer,
        params={"app_id": published_app.app_id, "reporter_id": context.alice.id, "status": "closed"},
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["id"] == bug_id
