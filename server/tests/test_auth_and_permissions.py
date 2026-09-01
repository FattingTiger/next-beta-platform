from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from conftest import DEFAULT_PASSWORD, NEW_PASSWORD, ApiContext, AuthTokens
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from beta_center.database import Database
from beta_center.main import create_app
from beta_center.models import AuditLog, AuthSession, AuthThrottle, User
from beta_center.routers import auth as auth_router
from beta_center.runtime import Runtime
from beta_center.security import aware_utc
from beta_center.services.storage import LocalStorage


def error_code(response: object) -> str:
    return response.json()["error"]["code"]  # type: ignore[attr-defined,no-any-return]


def test_first_login_requires_password_change_and_revokes_initial_session(context: ApiContext) -> None:
    initial = context.login(context.forced)

    me = context.client.get("/api/v1/auth/me", headers=initial.bearer)
    assert me.status_code == 200
    assert me.json()["must_change_password"] is True

    blocked = context.client.get("/api/v1/apps", headers=initial.bearer)
    assert blocked.status_code == 403
    assert error_code(blocked) == "password_change_required"

    changed = context.client.post(
        "/api/v1/auth/change-password",
        headers=initial.bearer,
        json={"current_password": context.forced.password, "new_password": NEW_PASSWORD},
    )
    assert changed.status_code == 204
    assert context.client.get("/api/v1/auth/me", headers=initial.bearer).status_code == 401

    expired_refresh = context.client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": initial.refresh_token},
    )
    assert expired_refresh.status_code == 401
    assert error_code(expired_refresh) == "invalid_refresh"

    old_password = context.client.post(
        "/api/v1/auth/login",
        json={"phone": context.forced.phone, "password": context.forced.password},
    )
    assert old_password.status_code == 401
    assert error_code(old_password) == "invalid_credentials"

    current = context.login(context.forced, NEW_PASSWORD)
    assert context.client.get("/api/v1/apps", headers=current.bearer).json() == []
    changed_me = context.client.get("/api/v1/auth/me", headers=current.bearer)
    assert changed_me.json()["must_change_password"] is False


def test_upload_permission_subrequests_reject_bodies_before_nginx_streams_them(
    context: ApiContext,
) -> None:
    admin = context.login(context.admin)
    tester = context.login(context.alice)
    must_change = context.login(context.forced)

    admin_allowed = context.client.get(
        "/api/v1/auth/upload-permission/admin",
        headers=admin.bearer,
    )
    assert admin_allowed.status_code == 204
    assert admin_allowed.content == b""

    tester_denied = context.client.get(
        "/api/v1/auth/upload-permission/admin",
        headers=tester.bearer,
    )
    assert tester_denied.status_code == 403
    assert error_code(tester_denied) == "admin_required"

    must_change_admin_denied = context.client.get(
        "/api/v1/auth/upload-permission/admin",
        headers=must_change.bearer,
    )
    assert must_change_admin_denied.status_code == 403
    assert error_code(must_change_admin_denied) == "password_change_required"

    for auth in (tester, admin):
        user_allowed = context.client.get(
            "/api/v1/auth/upload-permission/user",
            headers=auth.bearer,
        )
        assert user_allowed.status_code == 204
        assert user_allowed.content == b""

    must_change_denied = context.client.get(
        "/api/v1/auth/upload-permission/user",
        headers=must_change.bearer,
    )
    assert must_change_denied.status_code == 403
    assert error_code(must_change_denied) == "password_change_required"

    context.client.cookies.clear()
    anonymous = context.client.get("/api/v1/auth/upload-permission/user")
    assert anonymous.status_code == 401
    assert error_code(anonymous) == "not_authenticated"


def test_refresh_rotates_secret_and_logout_all_revokes_every_session(context: ApiContext) -> None:
    first = context.login(context.alice)
    second = context.login(context.alice)

    refreshed_response = context.client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": first.refresh_token},
    )
    assert refreshed_response.status_code == 200
    refreshed_payload = refreshed_response.json()
    refreshed = AuthTokens(
        access_token=refreshed_payload["access_token"],
        refresh_token=refreshed_payload["refresh_token"],
        csrf_token=refreshed_payload["csrf_token"],
    )
    assert refreshed.refresh_token != first.refresh_token
    assert refreshed.csrf_token != first.csrf_token

    replay = context.client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": first.refresh_token},
    )
    assert replay.status_code == 401
    assert error_code(replay) == "invalid_refresh"

    logout_all = context.client.post("/api/v1/auth/logout-all", headers=second.bearer)
    assert logout_all.status_code == 204
    for token in (first.access_token, second.access_token, refreshed.access_token):
        response = context.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401
    for refresh_token in (second.refresh_token, refreshed.refresh_token):
        response = context.client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert response.status_code == 401

    with context.runtime.database.session() as db:
        active_sessions = db.scalar(
            select(func.count(AuthSession.id)).where(
                AuthSession.user_id == context.alice.id,
                AuthSession.revoked_at.is_(None),
            )
        )
        assert active_sessions == 0


def test_reauthenticate_rejects_wrong_password_and_non_admin_without_refreshing_session(
    context: ApiContext,
) -> None:
    admin = context.login(context.admin)
    with context.runtime.database.session() as db:
        admin_session = db.scalar(
            select(AuthSession).where(
                AuthSession.user_id == context.admin.id,
                AuthSession.revoked_at.is_(None),
            )
        )
        assert admin_session is not None
        original_reauthenticated_at = admin_session.reauthenticated_at

    wrong = context.client.post(
        "/api/v1/auth/reauthenticate",
        headers={**admin.bearer, "X-Request-ID": "reauth-wrong-password"},
        json={"password": "Definitely-Wrong-9!"},
    )
    assert wrong.status_code == 400
    assert error_code(wrong) == "current_password_invalid"

    with context.runtime.database.session() as db:
        admin_session = db.scalar(
            select(AuthSession).where(
                AuthSession.user_id == context.admin.id,
                AuthSession.revoked_at.is_(None),
            )
        )
        assert admin_session is not None
        assert admin_session.reauthenticated_at == original_reauthenticated_at
        failure = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "auth.reauthenticate",
                AuditLog.actor_id == context.admin.id,
                AuditLog.outcome == "failure",
            )
        )
        assert failure is not None
        assert failure.entity_id == admin_session.id
        assert failure.reason_code == "invalid_password"
        assert failure.request_id == "reauth-wrong-password"

    tester = context.login(context.alice)
    denied = context.client.post(
        "/api/v1/auth/reauthenticate",
        headers=tester.bearer,
        json={"password": context.alice.password},
    )
    assert denied.status_code == 403
    assert error_code(denied) == "admin_required"


def test_admin_reauth_session_limit_persists_and_short_circuits_password_hashing(
    context: ApiContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin = context.login(context.admin)
    settings = context.runtime.settings
    settings.admin_reauth_session_failure_limit = 3
    settings.admin_reauth_user_failure_limit = 100
    settings.admin_reauth_ip_failure_limit = 500
    actual_verify_password = auth_router.verify_password
    verify_calls = 0

    def counted_verify_password(password: str, encoded_hash: str) -> bool:
        nonlocal verify_calls
        verify_calls += 1
        return actual_verify_password(password, encoded_hash)

    monkeypatch.setattr(auth_router, "verify_password", counted_verify_password)
    for attempt in range(settings.admin_reauth_session_failure_limit):
        rejected = context.client.post(
            "/api/v1/auth/reauthenticate",
            headers=admin.bearer,
            json={"password": "Definitely-Wrong-9!"},
        )
        assert rejected.status_code == 400
        assert error_code(rejected) == "current_password_invalid"
        assert verify_calls == attempt + 1

    with context.runtime.database.session() as db:
        rows = list(db.scalars(select(AuthThrottle).where(AuthThrottle.scope.like("admin_reauth_%"))))
        assert {row.scope for row in rows} == {
            "admin_reauth_session",
            "admin_reauth_user",
            "admin_reauth_ip",
        }
        by_scope = {row.scope: row for row in rows}
        assert all(row.failure_count == settings.admin_reauth_session_failure_limit for row in rows)
        assert by_scope["admin_reauth_session"].locked_until is not None
        assert by_scope["admin_reauth_user"].locked_until is None
        assert by_scope["admin_reauth_ip"].locked_until is None

    limited = context.client.post(
        "/api/v1/auth/reauthenticate",
        headers=admin.bearer,
        json={"password": context.admin.password},
    )
    assert limited.status_code == 429
    assert error_code(limited) == "admin_reauth_rate_limited"
    assert limited.headers["retry-after"] == str(settings.admin_reauth_lock_minutes * 60)
    assert verify_calls == settings.admin_reauth_session_failure_limit

    second_database = Database(settings)
    second_runtime = Runtime(
        settings=settings,
        database=second_database,
        storage=LocalStorage(settings.storage_root),
        apk_inspector=context.runtime.apk_inspector,
        login_limiter=type(context.runtime.login_limiter)(),
    )
    second_app = create_app(settings, runtime=second_runtime)
    with TestClient(second_app, raise_server_exceptions=False) as second_client:
        still_limited = second_client.post(
            "/api/v1/auth/reauthenticate",
            headers=admin.bearer,
            json={"password": context.admin.password},
        )
    assert still_limited.status_code == 429
    assert error_code(still_limited) == "admin_reauth_rate_limited"
    assert still_limited.headers["retry-after"] == str(settings.admin_reauth_lock_minutes * 60)
    assert verify_calls == settings.admin_reauth_session_failure_limit


def test_successful_admin_reauth_clears_session_and_user_throttles_but_preserves_ip(
    context: ApiContext,
) -> None:
    admin = context.login(context.admin)
    rejected = context.client.post(
        "/api/v1/auth/reauthenticate",
        headers=admin.bearer,
        json={"password": "Definitely-Wrong-9!"},
    )
    assert rejected.status_code == 400

    with context.runtime.database.session() as db:
        before = list(db.scalars(select(AuthThrottle).where(AuthThrottle.scope.like("admin_reauth_%"))))
        assert {row.scope for row in before} == {
            "admin_reauth_session",
            "admin_reauth_user",
            "admin_reauth_ip",
        }
        assert all(row.failure_count == 1 for row in before)
        ip_key = next(row.key_hash for row in before if row.scope == "admin_reauth_ip")

    accepted = context.client.post(
        "/api/v1/auth/reauthenticate",
        headers=admin.bearer,
        json={"password": context.admin.password},
    )
    assert accepted.status_code == 204

    with context.runtime.database.session() as db:
        remaining = list(db.scalars(select(AuthThrottle).where(AuthThrottle.scope.like("admin_reauth_%"))))
        assert len(remaining) == 1
        assert remaining[0].scope == "admin_reauth_ip"
        assert remaining[0].key_hash == ip_key
        assert remaining[0].failure_count == 1
        assert remaining[0].locked_until is None


def test_change_password_session_limit_persists_and_short_circuits_password_hashing(
    context: ApiContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth = context.login(context.alice)
    settings = context.runtime.settings
    settings.password_change_session_failure_limit = 3
    settings.password_change_user_failure_limit = 100
    settings.password_change_ip_failure_limit = 500
    actual_verify_password = auth_router.verify_password
    verify_calls = 0

    def counted_verify_password(password: str, encoded_hash: str) -> bool:
        nonlocal verify_calls
        verify_calls += 1
        return actual_verify_password(password, encoded_hash)

    monkeypatch.setattr(auth_router, "verify_password", counted_verify_password)
    payload = {
        "current_password": "Definitely-Wrong-9!",
        "new_password": NEW_PASSWORD,
    }
    for attempt in range(settings.password_change_session_failure_limit):
        rejected = context.client.post(
            "/api/v1/auth/change-password",
            headers=auth.bearer,
            json=payload,
        )
        assert rejected.status_code == 400
        assert error_code(rejected) == "current_password_invalid"
        assert verify_calls == attempt + 1

    with context.runtime.database.session() as db:
        rows = list(db.scalars(select(AuthThrottle).where(AuthThrottle.scope.like("pwd_change_%"))))
        assert {row.scope for row in rows} == {
            "pwd_change_session",
            "pwd_change_user",
            "pwd_change_ip",
        }
        by_scope = {row.scope: row for row in rows}
        assert all(row.failure_count == settings.password_change_session_failure_limit for row in rows)
        assert by_scope["pwd_change_session"].locked_until is not None
        assert by_scope["pwd_change_user"].locked_until is None
        assert by_scope["pwd_change_ip"].locked_until is None

    limited = context.client.post(
        "/api/v1/auth/change-password",
        headers=auth.bearer,
        json={"current_password": context.alice.password, "new_password": NEW_PASSWORD},
    )
    assert limited.status_code == 429
    assert error_code(limited) == "password_change_rate_limited"
    assert limited.headers["retry-after"] == str(settings.password_change_lock_minutes * 60)
    assert verify_calls == settings.password_change_session_failure_limit

    second_database = Database(settings)
    second_runtime = Runtime(
        settings=settings,
        database=second_database,
        storage=LocalStorage(settings.storage_root),
        apk_inspector=context.runtime.apk_inspector,
        login_limiter=type(context.runtime.login_limiter)(),
    )
    second_app = create_app(settings, runtime=second_runtime)
    with TestClient(second_app, raise_server_exceptions=False) as second_client:
        still_limited = second_client.post(
            "/api/v1/auth/change-password",
            headers=auth.bearer,
            json={"current_password": context.alice.password, "new_password": NEW_PASSWORD},
        )
    assert still_limited.status_code == 429
    assert error_code(still_limited) == "password_change_rate_limited"
    assert still_limited.headers["retry-after"] == str(settings.password_change_lock_minutes * 60)
    assert verify_calls == settings.password_change_session_failure_limit


def test_successful_password_change_clears_session_and_user_throttles_but_preserves_ip(
    context: ApiContext,
) -> None:
    auth = context.login(context.alice)
    rejected = context.client.post(
        "/api/v1/auth/change-password",
        headers=auth.bearer,
        json={"current_password": "Definitely-Wrong-9!", "new_password": NEW_PASSWORD},
    )
    assert rejected.status_code == 400

    with context.runtime.database.session() as db:
        before = list(db.scalars(select(AuthThrottle).where(AuthThrottle.scope.like("pwd_change_%"))))
        assert {row.scope for row in before} == {
            "pwd_change_session",
            "pwd_change_user",
            "pwd_change_ip",
        }
        assert all(row.failure_count == 1 for row in before)
        ip_key = next(row.key_hash for row in before if row.scope == "pwd_change_ip")

    accepted = context.client.post(
        "/api/v1/auth/change-password",
        headers=auth.bearer,
        json={"current_password": context.alice.password, "new_password": NEW_PASSWORD},
    )
    assert accepted.status_code == 204

    with context.runtime.database.session() as db:
        remaining = list(db.scalars(select(AuthThrottle).where(AuthThrottle.scope.like("pwd_change_%"))))
        assert len(remaining) == 1
        assert remaining[0].scope == "pwd_change_ip"
        assert remaining[0].key_hash == ip_key
        assert remaining[0].failure_count == 1
        assert remaining[0].locked_until is None


def test_stale_admin_session_requires_reauthentication_before_high_risk_write(
    context: ApiContext,
) -> None:
    admin = context.login(context.admin)
    stale_at = datetime.now(UTC) - timedelta(minutes=context.runtime.settings.admin_reauth_minutes + 1)
    with context.runtime.database.session() as db:
        admin_session = db.scalar(
            select(AuthSession).where(
                AuthSession.user_id == context.admin.id,
                AuthSession.revoked_at.is_(None),
            )
        )
        assert admin_session is not None
        session_id = admin_session.id
        admin_session.reauthenticated_at = stale_at

    payload = {
        "name": "需要重新认证的测试组",
        "description": "高风险操作契约",
        "member_ids": [],
        "app_ids": [],
    }
    blocked = context.client.post(
        "/api/v1/admin/groups",
        headers=admin.bearer,
        json=payload,
    )
    assert blocked.status_code == 403
    assert error_code(blocked) == "admin_reauthentication_required"

    refreshed = context.client.post(
        "/api/v1/auth/reauthenticate",
        headers={**admin.bearer, "X-Request-ID": "reauth-success"},
        json={"password": context.admin.password},
    )
    assert refreshed.status_code == 204
    assert refreshed.content == b""

    accepted = context.client.post(
        "/api/v1/admin/groups",
        headers=admin.bearer,
        json=payload,
    )
    assert accepted.status_code == 201
    assert accepted.json()["name"] == payload["name"]

    with context.runtime.database.session() as db:
        admin_session = db.get(AuthSession, session_id)
        assert admin_session is not None
        assert aware_utc(admin_session.reauthenticated_at) > stale_at
        success = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "auth.reauthenticate",
                AuditLog.actor_id == context.admin.id,
                AuditLog.outcome == "success",
            )
        )
        assert success is not None
        assert success.entity_id == session_id
        assert success.reason_code == ""
        assert success.request_id == "reauth-success"


def test_cookie_mutations_require_matching_csrf_but_bearer_does_not(context: ApiContext) -> None:
    context.client.cookies.clear()
    admin = context.login(context.admin)
    group_payload = {
        "name": "Cookie CSRF 组",
        "description": "",
        "member_ids": [],
        "app_ids": [],
    }

    missing = context.client.post("/api/v1/admin/groups", json=group_payload)
    assert missing.status_code == 403
    assert error_code(missing) == "csrf_failed"

    wrong = context.client.post(
        "/api/v1/admin/groups",
        headers={"X-CSRF-Token": "wrong-token"},
        json=group_payload,
    )
    assert wrong.status_code == 403
    assert error_code(wrong) == "csrf_failed"

    accepted = context.client.post(
        "/api/v1/admin/groups",
        headers={"X-CSRF-Token": admin.csrf_token},
        json=group_payload,
    )
    assert accepted.status_code == 201

    bearer = context.client.post(
        "/api/v1/admin/groups",
        headers=admin.bearer,
        json={**group_payload, "name": "Bearer 组"},
    )
    assert bearer.status_code == 201


def test_account_lockout_and_failure_audits_survive_rejected_requests(context: ApiContext) -> None:
    for _ in range(context.runtime.settings.login_failure_limit):
        response = context.client.post(
            "/api/v1/auth/login",
            json={"phone": context.alice.phone, "password": "Definitely-Wrong-9!"},
        )
        assert response.status_code == 401
        assert error_code(response) == "invalid_credentials"

    locked = context.client.post(
        "/api/v1/auth/login",
        json={"phone": context.alice.phone, "password": DEFAULT_PASSWORD},
    )
    assert locked.status_code == 429
    assert error_code(locked) == "login_locked"
    assert int(locked.headers["retry-after"]) > 0

    with context.runtime.database.session() as db:
        user = db.get(User, context.alice.id)
        assert user is not None
        assert user.locked_until is not None
        failures = db.scalar(
            select(func.count(AuditLog.id)).where(
                AuditLog.actor_id == context.alice.id,
                AuditLog.action == "auth.login",
                AuditLog.outcome == "failure",
            )
        )
        assert failures == context.runtime.settings.login_failure_limit


def test_tester_is_denied_all_admin_collections(context: ApiContext) -> None:
    tester = context.login(context.alice)
    for path in (
        "/api/v1/admin/users",
        "/api/v1/admin/groups",
        "/api/v1/admin/apps",
        "/api/v1/admin/bugs",
        "/api/v1/admin/dashboard",
        "/api/v1/admin/downloads",
        "/api/v1/admin/audit-logs",
    ):
        response = context.client.get(path, headers=tester.bearer)
        assert response.status_code == 403, path
        assert error_code(response) == "admin_required"


def test_admin_user_group_lifecycle_and_session_revocation(context: ApiContext) -> None:
    admin = context.login(context.admin)
    group = context.create_group(admin, name="权限测试组")
    create_response = context.client.post(
        "/api/v1/admin/users",
        headers=admin.bearer,
        json={
            "display_name": "新内测用户",
            "phone": "+8613900000123",
            "initial_password": "New-Tester-Password-3!",
            "role": "tester",
            "group_ids": [group["id"], group["id"]],
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["must_change_password"] is True
    assert created["group_ids"] == [group["id"]]

    duplicate = context.client.post(
        "/api/v1/admin/users",
        headers=admin.bearer,
        json={
            "display_name": "重复手机号",
            "phone": "+8613900000123",
            "initial_password": "Other-Password-4!",
        },
    )
    assert duplicate.status_code == 409
    assert error_code(duplicate) == "phone_exists"

    login = context.client.post(
        "/api/v1/auth/login",
        json={"phone": created["phone"], "password": "New-Tester-Password-3!"},
    )
    assert login.status_code == 200
    old_access = login.json()["access_token"]

    disabled = context.client.patch(
        f"/api/v1/admin/users/{created['id']}",
        headers=admin.bearer,
        json={"is_active": False},
    )
    assert disabled.status_code == 200
    assert disabled.json()["is_active"] is False
    assert (
        context.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {old_access}"},
        ).status_code
        == 401
    )

    self_disable = context.client.patch(
        f"/api/v1/admin/users/{context.admin.id}",
        headers=admin.bearer,
        json={"is_active": False},
    )
    assert self_disable.status_code == 400
    assert error_code(self_disable) == "cannot_disable_self"


def test_group_rejects_unknown_assignments_without_partial_creation(context: ApiContext) -> None:
    admin = context.login(context.admin)
    response = context.client.post(
        "/api/v1/admin/groups",
        headers=admin.bearer,
        json={
            "name": "不能残留的组",
            "description": "",
            "member_ids": ["missing-user"],
            "app_ids": [],
        },
    )
    assert response.status_code == 400
    assert error_code(response) == "invalid_assignment_ids"

    listing = context.client.get("/api/v1/admin/groups?search=不能残留", headers=admin.bearer)
    assert listing.status_code == 200
    assert listing.json()["total"] == 0
