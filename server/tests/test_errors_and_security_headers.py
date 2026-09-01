from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from conftest import ApiContext
from fastapi import Request
from pydantic import SecretStr
from sqlalchemy import func, select

from beta_center.config import Settings
from beta_center.dependencies import get_db, request_ip
from beta_center.models import AuditLog

REQUIRED_SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "same-origin",
    "permissions-policy": "camera=(), microphone=(), geolocation=()",
}


def assert_error_envelope(response: object, *, status: int, code: str, request_id: str | None = None) -> None:
    assert response.status_code == status  # type: ignore[attr-defined]
    payload = response.json()  # type: ignore[attr-defined]
    assert set(payload) == {"error"}
    assert payload["error"]["code"] == code
    assert isinstance(payload["error"]["message"], str)
    assert payload["error"]["message"]
    assert payload["error"]["request_id"]
    if request_id is not None:
        assert payload["error"]["request_id"] == request_id


def assert_security_headers(response: object) -> None:
    for name, value in REQUIRED_SECURITY_HEADERS.items():
        assert response.headers[name] == value  # type: ignore[attr-defined]
    csp = response.headers["content-security-policy"]  # type: ignore[attr-defined]
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "base-uri 'self'" in csp


def test_unauthenticated_api_error_has_stable_envelope_headers_and_request_id(
    context: ApiContext,
) -> None:
    context.client.cookies.clear()
    response = context.client.get(
        "/api/v1/apps",
        headers={"X-Request-ID": "pytest-trace-001"},
    )
    assert_error_envelope(
        response,
        status=401,
        code="not_authenticated",
        request_id="pytest-trace-001",
    )
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-request-id"] == "pytest-trace-001"
    assert_security_headers(response)


def test_validation_error_lists_fields_without_echoing_sensitive_values(context: ApiContext) -> None:
    secret = "Never-Echo-This-Password-7!"
    response = context.client.post(
        "/api/v1/auth/login",
        headers={"X-Request-ID": "validation-case"},
        json={"phone": "invalid phone", "password": secret, "unexpected": "also-secret"},
    )
    assert_error_envelope(
        response,
        status=422,
        code="validation_error",
        request_id="validation-case",
    )
    assert set(response.json()["error"]["fields"]) == {"phone", "unexpected"}
    assert secret not in response.text
    assert "also-secret" not in response.text
    assert_security_headers(response)


def test_unknown_api_route_uses_same_error_contract(context: ApiContext) -> None:
    response = context.client.get(
        "/api/v1/does-not-exist",
        headers={"X-Request-ID": "missing-route"},
    )
    assert_error_envelope(
        response,
        status=404,
        code="request_failed",
        request_id="missing-route",
    )
    assert response.headers["cache-control"] == "no-store"
    assert_security_headers(response)


def test_unexpected_error_is_redacted_and_correlated(context: ApiContext) -> None:
    admin = context.login(context.admin)
    sensitive_detail = "database-password=do-not-leak"

    def explode_database():  # type: ignore[no-untyped-def]
        raise RuntimeError(sensitive_detail)

    context.app.dependency_overrides[get_db] = explode_database  # type: ignore[attr-defined]
    try:
        response = context.client.get(
            "/api/v1/admin/users",
            headers={**admin.bearer, "X-Request-ID": "internal-case"},
        )
    finally:
        context.app.dependency_overrides.pop(get_db, None)  # type: ignore[attr-defined]

    assert_error_envelope(
        response,
        status=500,
        code="internal_error",
        request_id="internal-case",
    )
    assert sensitive_detail not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert_security_headers(response)


def test_request_id_is_bounded_and_health_responses_receive_hardening_headers(
    context: ApiContext,
) -> None:
    supplied = "r" * 200
    health = context.client.get("/health/live", headers={"X-Request-ID": supplied})
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.headers["x-request-id"] == "r" * 80
    assert "cache-control" not in health.headers
    assert_security_headers(health)

    ready = context.client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json()["checks"] == {"database": "ok", "storage": "ok", "apk_tools": "ok"}
    assert_security_headers(ready)


def test_admin_shell_cache_busts_assets_and_admin_assets_are_not_cached(context: ApiContext) -> None:
    shell = context.client.get("/admin")
    assert shell.status_code == 200
    assert shell.headers["cache-control"] == "no-store"
    assert "/admin/assets/admin.css?v=" in shell.text
    assert "/admin/assets/admin.js?v=" in shell.text

    script = context.client.get("/admin/assets/admin.js")
    assert script.status_code == 200
    assert script.headers["cache-control"] == "no-store"


def test_auth_cookies_are_http_only_where_required_and_strict_same_site(context: ApiContext) -> None:
    context.client.cookies.clear()
    response = context.client.post(
        "/api/v1/auth/login",
        json={"phone": context.alice.phone, "password": context.alice.password},
    )
    assert response.status_code == 200
    cookie_headers = response.headers.get_list("set-cookie")
    access_cookie = next(item for item in cookie_headers if item.startswith("beta_access="))
    refresh_cookie = next(item for item in cookie_headers if item.startswith("beta_refresh="))
    csrf_cookie = next(item for item in cookie_headers if item.startswith("beta_csrf="))
    for cookie in (access_cookie, refresh_cookie, csrf_cookie):
        assert "SameSite=strict" in cookie
    assert "HttpOnly" in access_cookie
    assert "HttpOnly" in refresh_cookie
    assert "HttpOnly" not in csrf_cookie
    assert "Path=/api/v1/auth" in refresh_cookie


def test_bearer_token_is_not_accepted_from_query_string(context: ApiContext) -> None:
    auth = context.login(context.alice)
    context.client.cookies.clear()
    response = context.client.get(
        "/api/v1/apps",
        params={"access_token": auth.access_token},
    )
    assert_error_envelope(response, status=401, code="not_authenticated")
    assert auth.access_token not in response.text


def test_login_failure_audit_preserves_correlation_and_all_management_filters(
    context: ApiContext,
) -> None:
    request_id = "audit-login-failure-001"
    before = datetime.now(UTC) - timedelta(minutes=1)
    rejected = context.client.post(
        "/api/v1/auth/login",
        headers={"X-Request-ID": request_id},
        json={"phone": "+8613999999998", "password": "Unknown-Password-8!"},
    )
    after = datetime.now(UTC) + timedelta(minutes=1)
    assert_error_envelope(
        rejected,
        status=401,
        code="invalid_credentials",
        request_id=request_id,
    )

    admin = context.login(context.admin)
    response = context.client.get(
        "/api/v1/admin/audit-logs",
        headers=admin.bearer,
        params={
            "action": "auth.login",
            "outcome": "failure",
            "reason_code": "invalid_credentials",
            "request_id": request_id,
            "entity_type": "user",
            "created_from": before.isoformat(),
            "created_to": after.isoformat(),
        },
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1
    [entry] = response.json()["items"]
    assert entry["actor_id"] is None
    assert entry["action"] == "auth.login"
    assert entry["entity_type"] == "user"
    assert entry["outcome"] == "failure"
    assert entry["reason_code"] == "invalid_credentials"
    assert entry["request_id"] == request_id
    assert entry["details"] == {"phone_suffix": "9998"}

    mismatched = context.client.get(
        "/api/v1/admin/audit-logs",
        headers=admin.bearer,
        params={"request_id": request_id, "entity_id": context.alice.id},
    )
    assert mismatched.status_code == 200
    assert mismatched.json()["total"] == 0


def test_rejected_admin_write_audit_records_actor_reason_request_and_filterable_details(
    context: ApiContext,
) -> None:
    admin = context.login(context.admin)
    request_id = "audit-admin-rejected-001"
    before = datetime.now(UTC) - timedelta(minutes=1)
    rejected = context.client.post(
        "/api/v1/admin/users",
        headers={**admin.bearer, "X-Request-ID": request_id},
        json={"display_name": "", "force_change": False},
    )
    after = datetime.now(UTC) + timedelta(minutes=1)
    assert_error_envelope(
        rejected,
        status=422,
        code="validation_error",
        request_id=request_id,
    )

    response = context.client.get(
        "/api/v1/admin/audit-logs",
        headers=admin.bearer,
        params={
            "action": "security.request_rejected",
            "actor_id": context.admin.id,
            "outcome": "failure",
            "reason_code": "validation_error",
            "request_id": request_id,
            "entity_type": "http_request",
            "created_from": before.isoformat(),
            "created_to": after.isoformat(),
        },
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1
    [entry] = response.json()["items"]
    assert entry["actor_id"] == context.admin.id
    assert entry["actor_name"] == context.admin.display_name
    assert entry["reason_code"] == "validation_error"
    assert entry["request_id"] == request_id
    assert entry["details"] == {
        "method": "POST",
        "path": "/api/v1/admin/users",
        "status": 422,
    }


def test_anonymous_and_unknown_admin_writes_do_not_create_rejected_operation_audits(
    context: ApiContext,
) -> None:
    context.client.cookies.clear()
    with context.runtime.database.session() as db:
        before = db.scalar(
            select(func.count(AuditLog.id)).where(AuditLog.action == "security.request_rejected")
        )

    valid_user = {
        "display_name": "匿名写入探针",
        "phone": "+8613900000099",
        "initial_password": "Probe-Password-9!",
        "role": "tester",
        "group_ids": [],
    }
    for index in range(5):
        known = context.client.post("/api/v1/admin/users", json=valid_user)
        unknown = context.client.post(f"/api/v1/admin/unknown-{index}", json={})
        assert known.status_code == 401
        assert unknown.status_code == 404

    with context.runtime.database.session() as db:
        after = db.scalar(
            select(func.count(AuditLog.id)).where(AuditLog.action == "security.request_rejected")
        )
    assert after == before


def test_production_proxy_ip_parsing_only_trusts_configured_peer_networks(tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = Settings(
        environment="production",
        database_url="postgresql+psycopg://beta@db/beta",
        storage_root=tmp_path / "storage",
        secret_key=SecretStr("production-secret-key-with-at-least-32-characters"),
        public_base_url="https://beta.example.test",
        cookie_secure=True,
        allowed_hosts=["beta.example.test"],
        trusted_proxy_networks=["10.0.0.0/8", "fd00::/8"],
        use_x_accel_redirect=True,
        auto_create_schema=False,
    )
    app = SimpleNamespace(state=SimpleNamespace(runtime=SimpleNamespace(settings=settings)))

    def build_request(peer: str, forwarded: str) -> Request:
        return Request(
            {
                "type": "http",
                "http_version": "1.1",
                "method": "GET",
                "scheme": "https",
                "path": "/",
                "raw_path": b"/",
                "query_string": b"",
                "root_path": "",
                "headers": [(b"x-forwarded-for", forwarded.encode())],
                "client": (peer, 50_000),
                "server": ("beta.example.test", 443),
                "app": app,
            }
        )

    assert request_ip(build_request("10.1.2.3", "203.0.113.77, 10.1.2.1")) == "203.0.113.77"
    assert request_ip(build_request("fd00::10", "2001:db8::7, fd00::2")) == "2001:db8::7"
    assert request_ip(build_request("192.0.2.10", "203.0.113.99")) == "192.0.2.10"
    assert request_ip(build_request("10.1.2.3", "not-an-ip")) == "10.1.2.3"
