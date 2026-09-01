from __future__ import annotations

from datetime import UTC, datetime, timedelta

from conftest import ApiContext, PublishedApp
from fastapi.testclient import TestClient
from sqlalchemy import select

from beta_center.database import Database
from beta_center.main import create_app
from beta_center.models import AuditLog, AuthSession, AuthThrottle, DownloadRecord, User
from beta_center.runtime import Runtime
from beta_center.services.storage import LocalStorage


def error_code(response: object) -> str:
    return response.json()["error"]["code"]  # type: ignore[attr-defined,no-any-return]


def test_unknown_login_throttle_persists_across_runtime_and_client_recreation(
    context: ApiContext,
) -> None:
    context.runtime.settings.login_identity_failure_limit = 1
    context.runtime.settings.login_ip_failure_limit = 100
    request = {"phone": "+8613999999999", "password": "Unknown-Password-8!"}
    first = context.client.post(
        "/api/v1/auth/login",
        headers={"X-Request-ID": "throttle-first-runtime"},
        json=request,
    )
    assert first.status_code == 401
    assert error_code(first) == "invalid_credentials"
    assert request["password"] not in first.text

    with context.runtime.database.session() as db:
        failure = db.scalar(
            select(AuditLog).where(
                AuditLog.actor_id.is_(None),
                AuditLog.action == "auth.login",
                AuditLog.outcome == "failure",
            )
        )
        assert failure is not None
        assert failure.details == {"phone_suffix": "9999"}
        throttle_rows = list(db.scalars(select(AuthThrottle).order_by(AuthThrottle.scope)))
        assert [row.scope for row in throttle_rows] == ["identity", "ip"]
        identity_row = next(row for row in throttle_rows if row.scope == "identity")
        assert identity_row.failure_count == 1
        assert identity_row.locked_until is not None
        assert all(request["phone"] not in row.key_hash for row in throttle_rows)

    second_database = Database(context.runtime.settings)
    second_runtime = Runtime(
        settings=context.runtime.settings,
        database=second_database,
        storage=LocalStorage(context.runtime.settings.storage_root),
        apk_inspector=context.runtime.apk_inspector,
        login_limiter=type(context.runtime.login_limiter)(),
    )
    second_app = create_app(context.runtime.settings, runtime=second_runtime)
    with TestClient(second_app, raise_server_exceptions=False) as second_client:
        limited = second_client.post(
            "/api/v1/auth/login",
            headers={"X-Request-ID": "throttle-second-runtime"},
            json=request,
        )
    assert limited.status_code == 429
    assert error_code(limited) == "login_rate_limited"
    assert limited.headers["retry-after"] == str(context.runtime.settings.login_lock_minutes * 60)


def test_cookie_refresh_requires_csrf_and_single_logout_revokes_session(context: ApiContext) -> None:
    context.client.cookies.clear()
    auth = context.login(context.alice)
    missing_csrf = context.client.post("/api/v1/auth/refresh", json={})
    assert missing_csrf.status_code == 403
    assert error_code(missing_csrf) == "csrf_failed"

    refreshed = context.client.post(
        "/api/v1/auth/refresh",
        headers={"X-CSRF-Token": auth.csrf_token},
        json={},
    )
    assert refreshed.status_code == 200
    refreshed_token = refreshed.json()["access_token"]
    refreshed_csrf = refreshed.json()["csrf_token"]
    assert refreshed_token != auth.access_token

    logout = context.client.post(
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": refreshed_csrf},
    )
    assert logout.status_code == 204
    assert (
        context.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {refreshed_token}"},
        ).status_code
        == 401
    )

    context.client.cookies.clear()
    no_refresh = context.client.post("/api/v1/auth/refresh", json={})
    assert no_refresh.status_code == 401
    assert error_code(no_refresh) == "invalid_refresh"


def test_wrong_current_password_does_not_revoke_valid_session(context: ApiContext) -> None:
    auth = context.login(context.alice)
    response = context.client.post(
        "/api/v1/auth/change-password",
        headers=auth.bearer,
        json={"current_password": "Wrong-Current-8!", "new_password": "Valid-New-Password-8!"},
    )
    assert response.status_code == 400
    assert error_code(response) == "current_password_invalid"
    assert context.client.get("/api/v1/auth/me", headers=auth.bearer).status_code == 200


def test_admin_updates_user_fields_role_and_password_with_session_revocation(context: ApiContext) -> None:
    admin = context.login(context.admin)
    bob = context.login(context.bob)
    group = context.create_group(admin, name="用户变更组")

    updated = context.client.patch(
        f"/api/v1/admin/users/{context.bob.id}",
        headers=admin.bearer,
        json={
            "display_name": "Bob 已更新",
            "phone": "+8613800000333",
            "group_ids": [group["id"]],
            "role": "admin",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["display_name"] == "Bob 已更新"
    assert updated.json()["phone"] == "+8613800000333"
    assert updated.json()["role"] == "admin"
    assert updated.json()["group_ids"] == [group["id"]]
    assert context.client.get("/api/v1/auth/me", headers=bob.bearer).status_code == 401

    invalid_groups = context.client.patch(
        f"/api/v1/admin/users/{context.alice.id}",
        headers=admin.bearer,
        json={"group_ids": ["missing-group"]},
    )
    assert invalid_groups.status_code == 400
    assert error_code(invalid_groups) == "invalid_group_ids"

    alice = context.login(context.alice)
    optional_force_change = context.client.post(
        f"/api/v1/admin/users/{context.alice.id}/reset-password",
        headers=admin.bearer,
        json={"new_password": "Rejected-Reset-Password-6!", "force_change": False},
    )
    assert optional_force_change.status_code == 422
    assert error_code(optional_force_change) == "validation_error"
    assert "force_change" in optional_force_change.json()["error"]["fields"]
    assert context.client.get("/api/v1/auth/me", headers=alice.bearer).status_code == 200

    reset = context.client.post(
        f"/api/v1/admin/users/{context.alice.id}/reset-password",
        headers=admin.bearer,
        json={"new_password": "Reset-Password-7!", "force_change": True},
    )
    assert reset.status_code == 204
    assert context.client.get("/api/v1/auth/me", headers=alice.bearer).status_code == 401
    replacement = context.client.post(
        "/api/v1/auth/login",
        json={"phone": context.alice.phone, "password": "Reset-Password-7!"},
    )
    assert replacement.status_code == 200
    assert replacement.json()["user"]["must_change_password"] is True
    blocked = context.client.get(
        "/api/v1/apps",
        headers={"Authorization": f"Bearer {replacement.json()['access_token']}"},
    )
    assert blocked.status_code == 403
    assert error_code(blocked) == "password_change_required"

    own_role = context.client.patch(
        f"/api/v1/admin/users/{context.admin.id}",
        headers=admin.bearer,
        json={"role": "tester"},
    )
    assert own_role.status_code == 400
    assert error_code(own_role) == "cannot_change_own_role"
    assert context.client.get("/api/v1/admin/users/missing", headers=admin.bearer).status_code == 404


def test_admin_app_metadata_assignment_and_missing_object_errors(context: ApiContext) -> None:
    admin = context.login(context.admin)
    group = context.create_group(admin, member_ids=[context.alice.id])
    app = context.create_app(admin, group_ids=[str(group["id"])])

    duplicate = context.client.post(
        "/api/v1/admin/apps",
        headers=admin.bearer,
        json={"name": "重复应用", "package_name": "com.example.beta", "group_ids": []},
    )
    assert duplicate.status_code == 409
    assert error_code(duplicate) == "package_exists"

    update = context.client.patch(
        f"/api/v1/admin/apps/{app['id']}",
        headers=admin.bearer,
        json={
            "name": "协作台 Pro",
            "short_description": "更新后的简介",
            "description": "更新后的完整说明",
            "group_ids": [],
            "status": "archived",
        },
    )
    assert update.status_code == 200
    assert update.json()["name"] == "协作台 Pro"
    assert update.json()["short_description"] == "更新后的简介"
    assert update.json()["description"] == "更新后的完整说明"
    assert update.json()["group_ids"] == []
    assert update.json()["status"] == "archived"

    invalid_group = context.client.patch(
        f"/api/v1/admin/apps/{app['id']}",
        headers=admin.bearer,
        json={"group_ids": ["missing-group"]},
    )
    assert invalid_group.status_code == 400
    assert error_code(invalid_group) == "invalid_group_ids"
    assert context.client.get("/api/v1/admin/apps/missing", headers=admin.bearer).status_code == 404


def test_apk_and_screenshot_routes_reject_bad_names_types_and_missing_ids(context: ApiContext) -> None:
    admin = context.login(context.admin)
    group = context.create_group(admin)
    app = context.create_app(admin, group_ids=[str(group["id"])])
    base = f"/api/v1/admin/apps/{app['id']}"

    wrong_name = context.client.post(
        f"{base}/versions",
        headers=admin.bearer,
        files={"file": ("payload.zip", b"payload", "application/zip")},
    )
    assert wrong_name.status_code == 422
    assert error_code(wrong_name) == "invalid_upload"

    wrong_type = context.client.post(
        f"{base}/versions",
        headers=admin.bearer,
        files={"file": ("payload.apk", b"payload", "text/plain")},
    )
    assert wrong_type.status_code == 422
    assert error_code(wrong_type) == "invalid_upload"
    assert context.inspector.inspected_paths == []

    assert (
        context.client.post(
            f"{base}/versions/missing/publish",
            headers=admin.bearer,
            json={"release_notes": "不存在"},
        ).status_code
        == 404
    )
    assert (
        context.client.post(
            f"{base}/versions/missing/disable",
            headers=admin.bearer,
        ).status_code
        == 404
    )
    assert (
        context.client.delete(
            f"{base}/screenshots/missing",
            headers=admin.bearer,
        ).status_code
        == 404
    )


def test_bug_list_filters_comments_and_nonreporter_verification(
    context: ApiContext, published_app: PublishedApp
) -> None:
    created = context.client.post(
        "/api/v1/bugs",
        headers=published_app.alice_auth.bearer,
        data={
            "app_id": published_app.app_id,
            "version_id": published_app.version_id,
            "title": "筛选与回复测试",
            "description": "用于验证 mine、应用、状态和公开回复。",
        },
    )
    assert created.status_code == 201
    bug_id = created.json()["id"]
    listing = context.client.get(
        "/api/v1/bugs",
        headers=published_app.alice_auth.bearer,
        params={"mine": True, "app_id": published_app.app_id, "status": "pending", "page_size": 1},
    )
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["id"] == bug_id

    comment = context.client.post(
        f"/api/v1/bugs/{bug_id}/comments",
        headers=published_app.bob_auth.bearer,
        json={"content": "我也可以稳定复现"},
    )
    assert comment.status_code == 200
    assert comment.json()["comments"] == []
    reporter_detail = context.client.get(
        f"/api/v1/bugs/{bug_id}",
        headers=published_app.alice_auth.bearer,
    )
    assert reporter_detail.status_code == 200
    assert reporter_detail.json()["comments"][0]["content"] == "我也可以稳定复现"

    not_verifying = context.client.post(
        f"/api/v1/bugs/{bug_id}/verification",
        headers=published_app.alice_auth.bearer,
        json={"accepted": True, "note": "状态不正确"},
    )
    assert not_verifying.status_code == 409
    assert error_code(not_verifying) == "bug_not_verifying"
    assert (
        context.client.get("/api/v1/bugs/missing", headers=published_app.alice_auth.bearer).status_code == 404
    )


def test_download_terminal_states_expiry_and_authentication_are_enforced(
    context: ApiContext,
    published_app: PublishedApp,
) -> None:
    missing = context.client.post(
        "/api/v1/downloads",
        headers=published_app.alice_auth.bearer,
        json={"version_id": "missing-version"},
    )
    assert missing.status_code == 404
    outsider = context.login(context.outsider)
    denied = context.client.post(
        "/api/v1/downloads",
        headers=outsider.bearer,
        json={"version_id": published_app.version_id},
    )
    assert denied.status_code == 404

    start = context.client.post(
        "/api/v1/downloads",
        headers=published_app.alice_auth.bearer,
        json={"version_id": published_app.version_id},
    )
    assert start.status_code == 201
    ticket = start.json()
    context.client.cookies.clear()
    unauthenticated = context.client.get(ticket["url"])
    assert unauthenticated.status_code == 404

    with context.runtime.database.session() as db:
        record = db.get(DownloadRecord, ticket["download_id"])
        assert record is not None
        record.ticket_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    expired = context.client.get(ticket["url"], headers=published_app.alice_auth.bearer)
    assert expired.status_code == 404

    second = context.client.post(
        "/api/v1/downloads",
        headers=published_app.alice_auth.bearer,
        json={"version_id": published_app.version_id},
    ).json()
    cancelled = context.client.post(
        f"/api/v1/downloads/{second['download_id']}/failure",
        headers=published_app.alice_auth.bearer,
        json={"status": "cancelled", "reason": "用户取消"},
    )
    assert cancelled.status_code == 204
    same = context.client.post(
        f"/api/v1/downloads/{second['download_id']}/failure",
        headers=published_app.alice_auth.bearer,
        json={"status": "cancelled", "reason": "用户取消"},
    )
    assert same.status_code == 204
    different = context.client.post(
        f"/api/v1/downloads/{second['download_id']}/failure",
        headers=published_app.alice_auth.bearer,
        json={"status": "failed", "reason": "另一个结束原因"},
    )
    assert different.status_code == 409
    assert error_code(different) == "download_already_ended"
    complete_cancelled = context.client.post(
        f"/api/v1/downloads/{second['download_id']}/complete",
        headers=published_app.alice_auth.bearer,
        json={"sha256": second["sha256"], "bytes_received": second["file_size"]},
    )
    assert complete_cancelled.status_code == 409
    assert error_code(complete_cancelled) == "download_not_active"


def test_disabled_user_login_is_generic_and_existing_session_is_invalidated(context: ApiContext) -> None:
    auth = context.login(context.outsider)
    with context.runtime.database.session() as db:
        user = db.get(User, context.outsider.id)
        assert user is not None
        user.is_active = False
        user.session_generation += 1
        db.query(AuthSession).filter(AuthSession.user_id == user.id).update(
            {AuthSession.revoked_at: datetime.now(UTC)}
        )
    assert context.client.get("/api/v1/auth/me", headers=auth.bearer).status_code == 401
    login = context.client.post(
        "/api/v1/auth/login",
        json={"phone": context.outsider.phone, "password": context.outsider.password},
    )
    assert login.status_code == 401
    assert error_code(login) == "invalid_credentials"
    assert context.outsider.phone not in login.text


def test_admin_filtering_can_return_empty_pages_without_leaking_other_records(
    context: ApiContext,
    published_app: PublishedApp,
) -> None:
    users = context.client.get(
        "/api/v1/admin/users",
        headers=published_app.admin_auth.bearer,
        params={"active": False, "role": "admin", "page": 2, "page_size": 1},
    )
    assert users.status_code == 200
    assert users.json() == {"items": [], "total": 0, "page": 2, "page_size": 1}

    downloads = context.client.get(
        "/api/v1/admin/downloads",
        headers=published_app.admin_auth.bearer,
        params={"status": "failed", "user_id": context.outsider.id},
    )
    assert downloads.status_code == 200
    assert downloads.json()["total"] == 0
    audits = context.client.get(
        "/api/v1/admin/audit-logs",
        headers=published_app.admin_auth.bearer,
        params={"action": "does.not.exist", "actor_id": context.outsider.id},
    )
    assert audits.status_code == 200
    assert audits.json()["total"] == 0
