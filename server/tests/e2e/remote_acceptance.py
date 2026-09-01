#!/usr/bin/env python3
"""Destructive remote black-box acceptance test for Beta Center.

The runner creates randomly named acceptance data, exercises the public API and
gateway, then archives/deactivates the mutable records it created. Credentials,
bearer tokens, refresh tokens, CSRF tokens, and download tickets are never
printed. Prefer environment variables for passwords so they do not enter shell
history or the process list.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import secrets
import socket
import ssl
import sys
import tempfile
import threading
import time
import uuid
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar, cast
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import httpx

T = TypeVar("T")
SENSITIVE_QUERY_KEYS = {"access_token", "csrf_token", "password", "refresh_token", "ticket"}
API_PREFIX = "/api/v1"
DEFAULT_APK_PACKAGE = "com.example.betacenter.fixture"


class AcceptanceError(RuntimeError):
    """A contract assertion failed without exposing request secrets."""


class Redactor:
    def __init__(self, values: Iterable[str] = ()) -> None:
        self._values: set[str] = set()
        for value in values:
            self.add(value)

    def add(self, value: object) -> None:
        if isinstance(value, str) and len(value) >= 4:
            self._values.add(value)

    def redact(self, value: object) -> str:
        output = str(value)
        for secret_value in sorted(self._values, key=len, reverse=True):
            output = output.replace(secret_value, "<redacted>")
        return output


def require(condition: object, message: str) -> None:
    if not condition:
        raise AcceptanceError(message)


def json_object(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise AcceptanceError(f"response {response.status_code} is not valid JSON") from exc
    require(isinstance(payload, dict), "response JSON must be an object")
    return cast(dict[str, Any], payload)


def page_items(response: httpx.Response) -> list[dict[str, Any]]:
    payload = json_object(response)
    items = payload.get("items")
    require(isinstance(items, list), "page response is missing items")
    items = cast(list[Any], items)
    require(all(isinstance(item, dict) for item in items), "page items must be objects")
    return cast(list[dict[str, Any]], items)


def find_item(items: Iterable[dict[str, Any]], key: str, value: object) -> dict[str, Any] | None:
    return next((item for item in items if item.get(key) == value), None)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def bool_from_env(name: str, *, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise AcceptanceError(f"{name} must be a boolean")


def safe_url(value: str) -> str:
    parsed = urlsplit(value)
    query = [
        (key, "<redacted>" if key.lower() in SENSITIVE_QUERY_KEYS else item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
    ]
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), ""))


@dataclass(frozen=True, slots=True)
class Config:
    base_url: str
    admin_phone: str
    admin_password: str
    tester_phone: str
    tester_password: str
    apk_path: Path
    image_path: Path
    apk_package: str
    timeout: float
    insecure: bool
    ca_file: Path | None

    @property
    def verify(self) -> bool | str:
        if self.insecure:
            return False
        return str(self.ca_file) if self.ca_file else True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the destructive Beta Center remote black-box acceptance suite. "
            "Passwords should be supplied through BETA_ACCEPTANCE_* environment variables."
        ),
        formatter_class=argparse.HelpFormatter,
        epilog=(
            "Environment equivalents: BETA_ACCEPTANCE_BASE_URL, "
            "BETA_ACCEPTANCE_ADMIN_PHONE, BETA_ACCEPTANCE_ADMIN_PASSWORD, "
            "BETA_ACCEPTANCE_TESTER_PHONE, BETA_ACCEPTANCE_TESTER_PASSWORD, "
            "BETA_ACCEPTANCE_APK, BETA_ACCEPTANCE_IMAGE, "
            "BETA_ACCEPTANCE_APK_PACKAGE, BETA_ACCEPTANCE_TIMEOUT, "
            "BETA_ACCEPTANCE_CA_FILE, BETA_ACCEPTANCE_INSECURE."
        ),
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("BETA_ACCEPTANCE_BASE_URL"),
        help="final HTTPS origin (and optional path prefix) of Beta Center",
    )
    parser.add_argument(
        "--admin-phone",
        default=os.environ.get("BETA_ACCEPTANCE_ADMIN_PHONE"),
        help="existing active administrator phone",
    )
    parser.add_argument(
        "--admin-password",
        default=os.environ.get("BETA_ACCEPTANCE_ADMIN_PASSWORD"),
        help="administrator password; prefer its environment variable",
    )
    parser.add_argument(
        "--tester-phone",
        default=os.environ.get("BETA_ACCEPTANCE_TESTER_PHONE"),
        help="existing active tester phone",
    )
    parser.add_argument(
        "--tester-password",
        default=os.environ.get("BETA_ACCEPTANCE_TESTER_PASSWORD"),
        help="tester password; prefer its environment variable",
    )
    parser.add_argument(
        "--apk",
        default=os.environ.get("BETA_ACCEPTANCE_APK"),
        help="real signed APK fixture",
    )
    parser.add_argument(
        "--image",
        default=os.environ.get("BETA_ACCEPTANCE_IMAGE"),
        help="PNG/JPEG/WebP fixture reused for icon, screenshot, and Bug evidence",
    )
    parser.add_argument(
        "--apk-package",
        default=os.environ.get("BETA_ACCEPTANCE_APK_PACKAGE", DEFAULT_APK_PACKAGE),
        help=(
            "package name reported by the signed APK; it must exactly match the fixture "
            f"(default: {DEFAULT_APK_PACKAGE})"
        ),
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.environ.get("BETA_ACCEPTANCE_TIMEOUT", "120")),
        help="HTTP read/write timeout in seconds (default: 120)",
    )
    parser.add_argument(
        "--ca-file",
        default=os.environ.get("BETA_ACCEPTANCE_CA_FILE"),
        help="custom PEM CA bundle for the remote TLS endpoint",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        default=bool_from_env("BETA_ACCEPTANCE_INSECURE"),
        help="disable TLS certificate verification for isolated staging only",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run local MockTransport/socket safety checks without remote credentials",
    )
    return parser


def config_from_args(args: argparse.Namespace) -> Config:
    required_values = {
        "base URL": args.base_url,
        "admin phone": args.admin_phone,
        "admin password": args.admin_password,
        "tester phone": args.tester_phone,
        "tester password": args.tester_password,
        "signed APK": args.apk,
        "image": args.image,
    }
    missing = [label for label, value in required_values.items() if not value]
    require(not missing, f"missing required inputs: {', '.join(missing)}")

    parsed = urlsplit(str(args.base_url).strip())
    require(parsed.scheme in {"http", "https"} and parsed.hostname, "base URL must be HTTP(S)")
    require(not parsed.username and not parsed.password, "base URL must not contain credentials")
    require(not parsed.query and not parsed.fragment, "base URL must not contain query or fragment")
    normalized_base = urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))
    apk_path = Path(str(args.apk)).expanduser().resolve()
    image_path = Path(str(args.image)).expanduser().resolve()
    ca_file = Path(str(args.ca_file)).expanduser().resolve() if args.ca_file else None
    require(apk_path.is_file(), "signed APK path is not a file")
    require(apk_path.suffix.lower() == ".apk", "signed APK must use the .apk extension")
    require(apk_path.stat().st_size >= 32, "signed APK is unexpectedly small")
    with apk_path.open("rb") as apk_source:
        require(apk_source.read(2) == b"PK", "signed APK is not a ZIP/APK archive")
    require(image_path.is_file(), "image path is not a file")
    require(image_path.stat().st_size > 0, "image file is empty")
    require(not ca_file or ca_file.is_file(), "CA file path is not a file")
    require(args.timeout >= 5, "timeout must be at least 5 seconds")
    require(bool(args.apk_package and "." in args.apk_package), "APK package name is invalid")
    if parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise AcceptanceError("non-loopback remote acceptance requires HTTPS")
    return Config(
        base_url=normalized_base,
        admin_phone=str(args.admin_phone),
        admin_password=str(args.admin_password),
        tester_phone=str(args.tester_phone),
        tester_password=str(args.tester_password),
        apk_path=apk_path,
        image_path=image_path,
        apk_package=str(args.apk_package),
        timeout=float(args.timeout),
        insecure=bool(args.insecure),
        ca_file=ca_file,
    )


class ApiSession:
    def __init__(
        self,
        base_url: str,
        redactor: Redactor,
        *,
        verify: bool | str = True,
        timeout: float = 120,
        reauth_password: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.redactor = redactor
        self.reauth_password = reauth_password
        self.access_token: str | None = None
        self.refresh_token: str | None = None
        self.csrf_token: str | None = None
        self.user: dict[str, Any] | None = None
        self._origin = self._url_origin(self.base_url)
        self.client = httpx.Client(
            verify=verify,
            timeout=httpx.Timeout(timeout, connect=min(timeout, 15)),
            follow_redirects=False,
            headers={"User-Agent": "beta-center-remote-acceptance/1.0"},
            transport=transport,
        )

    def close(self) -> None:
        self.client.close()

    def full_url(self, path: str) -> str:
        if urlsplit(path).scheme:
            require(self._url_origin(path) == self._origin, "server returned a cross-origin URL")
            return path
        return urljoin(f"{self.base_url}/", path.lstrip("/"))

    def login(self, phone: str, password: str, *, client_name: str) -> dict[str, Any]:
        response = self.request(
            "POST",
            f"{API_PREFIX}/auth/login",
            expected=200,
            auth=False,
            json={"phone": phone, "password": password, "client_name": client_name},
        )
        payload = json_object(response)
        for key in ("access_token", "refresh_token", "csrf_token"):
            require(isinstance(payload.get(key), str) and payload[key], f"login response is missing {key}")
            self.redactor.add(payload[key])
        user = payload.get("user")
        require(isinstance(user, dict), "login response is missing user")
        self.access_token = cast(str, payload["access_token"])
        self.refresh_token = cast(str, payload["refresh_token"])
        self.csrf_token = cast(str, payload["csrf_token"])
        self.user = cast(dict[str, Any], user)
        return self.user

    def request(
        self,
        method: str,
        path: str,
        *,
        expected: int | Iterable[int],
        auth: bool = True,
        retry_reauth: bool = True,
        headers: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        expected_statuses = {expected} if isinstance(expected, int) else set(expected)
        request_headers = dict(headers or {})
        if auth:
            require(self.access_token, "authenticated request attempted before login")
            request_headers["Authorization"] = f"Bearer {self.access_token}"
        url = self.full_url(path)
        try:
            response = self.client.request(method, url, headers=request_headers, **kwargs)
        except httpx.HTTPError as exc:
            raise AcceptanceError(self.redactor.redact(f"{method} {safe_url(url)} failed: {exc}")) from exc
        if response.status_code in expected_statuses:
            return response
        code = self._error_code(response)
        if (
            auth
            and retry_reauth
            and response.status_code == 403
            and code == "admin_reauthentication_required"
            and self.reauth_password
        ):
            self._reauthenticate()
            return self.request(
                method,
                path,
                expected=expected_statuses,
                auth=auth,
                retry_reauth=False,
                headers=headers,
                **kwargs,
            )
        body = self.redactor.redact(response.text[:800])
        raise AcceptanceError(
            f"{method} {safe_url(url)} expected {sorted(expected_statuses)}, "
            f"got {response.status_code} (code={code or 'n/a'}, body={body!r})"
        )

    def _reauthenticate(self) -> None:
        require(self.reauth_password, "administrator reauthentication password is unavailable")
        response = self.request(
            "POST",
            f"{API_PREFIX}/auth/reauthenticate",
            expected=204,
            retry_reauth=False,
            json={"password": self.reauth_password},
        )
        require(not response.content, "reauthentication 204 response must be empty")

    @staticmethod
    def _error_code(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            return ""
        if not isinstance(payload, dict) or not isinstance(payload.get("error"), dict):
            return ""
        code = payload["error"].get("code")
        return code if isinstance(code, str) else ""

    @staticmethod
    def _url_origin(value: str) -> tuple[str, str, int]:
        parsed = urlsplit(value)
        default_port = 443 if parsed.scheme == "https" else 80
        return parsed.scheme, (parsed.hostname or "").lower(), parsed.port or default_port


def assert_error_code(response: httpx.Response, code: str) -> None:
    payload = json_object(response)
    error = payload.get("error")
    require(isinstance(error, dict), "error response is missing the error envelope")
    error = cast(dict[str, Any], error)
    require(error.get("code") == code, f"expected error code {code!r}")
    require(bool(error.get("request_id")), "error response is missing request_id")


def assert_security_headers(response: httpx.Response, *, api: bool = False, https: bool = False) -> None:
    expected = {
        "x-content-type-options": "nosniff",
        "x-frame-options": "DENY",
        "referrer-policy": "same-origin",
    }
    for name, value in expected.items():
        require(response.headers.get(name) == value, f"response is missing hardened header {name}")
    csp = response.headers.get("content-security-policy", "")
    require("default-src 'self'" in csp and "frame-ancestors 'none'" in csp, "CSP is incomplete")
    require(bool(response.headers.get("x-request-id")), "response is missing X-Request-ID")
    if api:
        require("no-store" in response.headers.get("cache-control", ""), "API response is cacheable")
    if https:
        require("max-age=" in response.headers.get("strict-transport-security", ""), "HSTS is missing")


def early_rejection_probe(
    base_url: str,
    *,
    endpoint: str,
    request_id: str,
    timeout: float,
    insecure: bool,
    ca_file: Path | None,
) -> int:
    """Send only headers for a declared 8 MiB upload and require a final response."""

    parsed = urlsplit(base_url)
    require(parsed.hostname is not None, "early-rejection URL has no host")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    base_path = parsed.path.rstrip("/")
    target = f"{base_path}/{endpoint.lstrip('/')}"
    host_header = parsed.netloc
    boundary = f"beta-acceptance-{uuid.uuid4().hex}"
    request = (
        f"POST {target} HTTP/1.1\r\n"
        f"Host: {host_header}\r\n"
        "User-Agent: beta-center-remote-acceptance/1.0\r\n"
        f"X-Request-ID: {request_id}\r\n"
        f"Content-Type: multipart/form-data; boundary={boundary}\r\n"
        f"Content-Length: {8 * 1024 * 1024}\r\n"
        "Expect: 100-continue\r\n"
        "Connection: close\r\n\r\n"
    ).encode("ascii")
    raw_socket = socket.create_connection((parsed.hostname, port), timeout=timeout)
    connection: socket.socket | ssl.SSLSocket = raw_socket
    try:
        if parsed.scheme == "https":
            if insecure:
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
            else:
                context = ssl.create_default_context(cafile=str(ca_file) if ca_file else None)
            connection = context.wrap_socket(raw_socket, server_hostname=parsed.hostname)
        connection.settimeout(timeout)
        connection.sendall(request)
        received = b""
        while b"\r\n\r\n" not in received:
            chunk = connection.recv(4096)
            if not chunk:
                break
            received += chunk
            require(len(received) <= 64 * 1024, "early-rejection response headers are too large")
    finally:
        connection.close()
    require(b"\r\n" in received, "gateway did not respond before the upload body")
    status_line = received.split(b"\r\n", maxsplit=1)[0].decode("ascii", errors="replace")
    parts = status_line.split()
    require(len(parts) >= 2 and parts[0].startswith("HTTP/"), "invalid early-rejection status line")
    try:
        status_code = int(parts[1])
    except ValueError as exc:
        raise AcceptanceError("invalid early-rejection status code") from exc
    require(status_code != 100, "gateway requested the anonymous upload body instead of rejecting early")
    return status_code


@dataclass(slots=True)
class RunState:
    tester_id: str | None = None
    outsider_id: str | None = None
    group_id: str | None = None
    app_id: str | None = None
    version_id: str | None = None
    screenshot_id: str | None = None
    icon_url: str | None = None
    screenshot_url: str | None = None
    download_id: str | None = None
    bug_id: str | None = None
    bug_attachment_url: str | None = None
    admin_rejection_id: str | None = None
    anonymous_rejection_id: str | None = None
    early_rejection_id: str | None = None
    cleanup_done: bool = False


@dataclass(slots=True)
class AcceptanceRunner:
    config: Config
    redactor: Redactor
    prefix: str = field(default_factory=lambda: f"ra-{time.strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(3)}")
    state: RunState = field(default_factory=RunState)
    steps_passed: int = 0
    admin: ApiSession = field(init=False)
    tester: ApiSession = field(init=False)
    outsider: ApiSession = field(init=False)
    anonymous: ApiSession = field(init=False)
    apk_size: int = field(init=False)
    apk_sha256: str = field(init=False)
    image_content_type: str = field(init=False)
    outsider_initial_password: str = field(init=False)
    outsider_password: str = field(init=False)
    outsider_phone: str = field(init=False)

    def __post_init__(self) -> None:
        self.redactor.add(self.config.admin_password)
        self.redactor.add(self.config.tester_password)
        self.admin = ApiSession(
            self.config.base_url,
            self.redactor,
            verify=self.config.verify,
            timeout=self.config.timeout,
            reauth_password=self.config.admin_password,
        )
        self.tester = ApiSession(
            self.config.base_url,
            self.redactor,
            verify=self.config.verify,
            timeout=self.config.timeout,
        )
        self.outsider = ApiSession(
            self.config.base_url,
            self.redactor,
            verify=self.config.verify,
            timeout=self.config.timeout,
        )
        self.anonymous = ApiSession(
            self.config.base_url,
            self.redactor,
            verify=self.config.verify,
            timeout=self.config.timeout,
        )
        self.apk_size = self.config.apk_path.stat().st_size
        self.apk_sha256 = file_sha256(self.config.apk_path)
        self.image_content_type = mimetypes.guess_type(self.config.image_path.name)[0] or "image/png"
        require(self.image_content_type.startswith("image/"), "image path has a non-image media type")
        self.outsider_initial_password = f"Aa9!{secrets.token_urlsafe(18)}"
        self.outsider_password = f"Bb8@{secrets.token_urlsafe(18)}"
        self.redactor.add(self.outsider_initial_password)
        self.redactor.add(self.outsider_password)
        self.outsider_phone = f"+86199{secrets.randbelow(100_000_000):08d}"

    def close(self) -> None:
        for session in (self.admin, self.tester, self.outsider, self.anonymous):
            session.close()

    def run(self) -> None:
        print(f"Beta Center remote acceptance prefix: {self.prefix}", flush=True)
        try:
            self._step("health, readiness, and response hardening", self._health)
            self._step("anonymous boundaries and upload early rejection", self._anonymous_boundaries)
            self._step("administrator login and rejected-operation audit seed", self._admin_login)
            self._step("tester identity and disposable user lifecycle", self._users)
            self._step("test group and application management", self._group_and_app)
            self._step("media uploads and non-admin upload denial", self._media)
            self._step("signed APK inspection and separate publication", self._apk_publish)
            self._step("catalog scope and private media authorization", self._catalog_scope)
            self._step("download ticket, Range transfer, integrity, and receipt", self._download)
            self._step("Bug evidence, comments, privacy, status, and verification", self._bugs)
            self._step("dashboard, download ledger, and audit trail", self._observability)
            self._step("archive and deactivate acceptance records", self._cleanup)
        except Exception:
            self._best_effort_cleanup()
            raise
        finally:
            self.close()
        print(f"PASS: {self.steps_passed} remote acceptance stages completed", flush=True)

    def _step(self, label: str, operation: Callable[[], None]) -> None:
        index = self.steps_passed + 1
        started = time.monotonic()
        print(f"[{index:02d}] {label} ...", flush=True)
        operation()
        self.steps_passed += 1
        print(f"[{index:02d}] PASS ({time.monotonic() - started:.2f}s)", flush=True)

    def _health(self) -> None:
        https = urlsplit(self.config.base_url).scheme == "https"
        live = self.anonymous.request("GET", "/health/live", expected=200, auth=False)
        assert_security_headers(live, https=https)
        live_payload = json_object(live)
        require(live_payload.get("status") == "ok" and live_payload.get("version"), "liveness failed")
        ready = self.anonymous.request("GET", "/health/ready", expected=200, auth=False)
        assert_security_headers(ready, https=https)
        ready_payload = json_object(ready)
        require(ready_payload.get("status") == "ok", "readiness status is not ok")
        checks = ready_payload.get("checks")
        require(isinstance(checks, dict), "readiness checks are missing")
        checks = cast(dict[str, Any], checks)
        for name in ("database", "storage", "apk_tools"):
            require(checks.get(name) == "ok", f"readiness check {name} is not ok")

    def _anonymous_boundaries(self) -> None:
        apps = self.anonymous.request("GET", f"{API_PREFIX}/apps", expected=401, auth=False)
        assert_error_code(apps, "not_authenticated")
        self.state.anonymous_rejection_id = f"{self.prefix}-anonymous-unknown"
        unknown = self.anonymous.request(
            "POST",
            f"{API_PREFIX}/admin/does-not-exist",
            expected=404,
            auth=False,
            headers={"X-Request-ID": self.state.anonymous_rejection_id},
            json={},
        )
        assert_error_code(unknown, "request_failed")
        protected = self.anonymous.request(
            "GET",
            f"/_protected-files/apks/{uuid.uuid4()}.apk",
            expected=404,
            auth=False,
        )
        require(protected.status_code == 404, "protected storage path is externally reachable")
        self.state.early_rejection_id = f"{self.prefix}-early-upload"
        status_code = early_rejection_probe(
            self.config.base_url,
            endpoint=f"{API_PREFIX}/admin/apps/{uuid.uuid4()}/icon",
            request_id=self.state.early_rejection_id,
            timeout=min(self.config.timeout, 20),
            insecure=self.config.insecure,
            ca_file=self.config.ca_file,
        )
        require(
            status_code == 401,
            f"anonymous upload headers were not rejected with 401 (got {status_code})",
        )

    def _admin_login(self) -> None:
        user = self.admin.login(
            self.config.admin_phone,
            self.config.admin_password,
            client_name=f"{self.prefix}-admin",
        )
        require(user.get("role") == "admin" and user.get("is_active") is True, "admin account is not active")
        require(user.get("must_change_password") is False, "admin account still requires a password change")
        dashboard = self.admin.request("GET", f"{API_PREFIX}/admin/dashboard", expected=200)
        dashboard_payload = json_object(dashboard)
        require(all(isinstance(value, int) for value in dashboard_payload.values()), "dashboard is malformed")
        self.state.admin_rejection_id = f"{self.prefix}-admin-rejected"
        rejected = self.admin.request(
            "POST",
            f"{API_PREFIX}/admin/groups",
            expected=422,
            headers={"X-Request-ID": self.state.admin_rejection_id},
            json={"name": "", "description": "", "member_ids": [], "app_ids": []},
        )
        assert_error_code(rejected, "validation_error")

    def _users(self) -> None:
        response = self.admin.request(
            "GET",
            f"{API_PREFIX}/admin/users",
            expected=200,
            params={"search": self.config.tester_phone, "page_size": 100},
        )
        tester_record = find_item(page_items(response), "phone", self.config.tester_phone)
        require(tester_record is not None, "configured tester was not found by the administrator")
        tester_record = cast(dict[str, Any], tester_record)
        require(tester_record.get("role") == "tester", "configured tester does not have tester role")
        require(tester_record.get("is_active") is True, "configured tester is inactive")
        require(
            tester_record.get("must_change_password") is False, "configured tester requires password change"
        )
        self.state.tester_id = cast(str, tester_record["id"])
        tester_user = self.tester.login(
            self.config.tester_phone,
            self.config.tester_password,
            client_name=f"{self.prefix}-tester",
        )
        require(tester_user.get("id") == self.state.tester_id, "tester login resolved a different user")

        created = self.admin.request(
            "POST",
            f"{API_PREFIX}/admin/users",
            expected=201,
            json={
                "display_name": f"{self.prefix} outsider",
                "phone": self.outsider_phone,
                "initial_password": self.outsider_initial_password,
                "role": "tester",
                "group_ids": [],
            },
        )
        created_user = json_object(created)
        self.state.outsider_id = cast(str, created_user.get("id"))
        require(bool(self.state.outsider_id), "created user has no id")
        require(
            created_user.get("must_change_password") is True, "new user must require first password change"
        )
        outsider_login = self.outsider.login(
            self.outsider_phone,
            self.outsider_initial_password,
            client_name=f"{self.prefix}-outsider-initial",
        )
        require(outsider_login.get("must_change_password") is True, "initial session is unexpectedly ready")
        blocked = self.outsider.request("GET", f"{API_PREFIX}/apps", expected=403)
        assert_error_code(blocked, "password_change_required")
        changed = self.outsider.request(
            "POST",
            f"{API_PREFIX}/auth/change-password",
            expected=204,
            json={
                "current_password": self.outsider_initial_password,
                "new_password": self.outsider_password,
            },
        )
        require(not changed.content, "password change 204 response must be empty")
        ready_user = self.outsider.login(
            self.outsider_phone,
            self.outsider_password,
            client_name=f"{self.prefix}-outsider-ready",
        )
        require(ready_user.get("must_change_password") is False, "password change did not make user ready")

    def _group_and_app(self) -> None:
        require(self.state.tester_id, "tester id is missing")
        group_response = self.admin.request(
            "POST",
            f"{API_PREFIX}/admin/groups",
            expected=201,
            json={
                "name": f"{self.prefix} group",
                "description": f"{self.prefix} remote acceptance group",
                "member_ids": [self.state.tester_id],
                "app_ids": [],
            },
        )
        group = json_object(group_response)
        self.state.group_id = cast(str, group.get("id"))
        require(group.get("member_ids") == [self.state.tester_id], "group assignment is incorrect")
        app_response = self.admin.request(
            "POST",
            f"{API_PREFIX}/admin/apps",
            expected=201,
            json={
                "name": f"{self.prefix} App",
                "package_name": self.config.apk_package,
                "short_description": f"{self.prefix} signed build",
                "description": f"{self.prefix} remote black-box acceptance application",
                "group_ids": [self.state.group_id],
            },
        )
        app = json_object(app_response)
        self.state.app_id = cast(str, app.get("id"))
        require(app.get("status") == "draft", "new application is not a draft")
        require(app.get("package_name") == self.config.apk_package, "application package changed")
        require(app.get("group_ids") == [self.state.group_id], "application group scope is incorrect")

    def _image_file(self) -> dict[str, tuple[str, Any, str]]:
        return {
            "file": (
                self.config.image_path.name,
                self.config.image_path.open("rb"),
                self.image_content_type,
            )
        }

    @staticmethod
    def _close_files(files: Mapping[str, tuple[str, Any, str]]) -> None:
        for _filename, file_object, _content_type in files.values():
            file_object.close()

    def _media(self) -> None:
        require(self.state.app_id, "app id is missing")
        unauthorized_files = self._image_file()
        try:
            denied = self.tester.request(
                "POST",
                f"{API_PREFIX}/admin/apps/{self.state.app_id}/icon",
                expected=403,
                files=unauthorized_files,
            )
        finally:
            self._close_files(unauthorized_files)
        require(denied.status_code == 403, "tester upload was not denied")

        icon_files = self._image_file()
        try:
            icon_response = self.admin.request(
                "POST",
                f"{API_PREFIX}/admin/apps/{self.state.app_id}/icon",
                expected=200,
                files=icon_files,
            )
        finally:
            self._close_files(icon_files)
        icon_app = json_object(icon_response)
        self.state.icon_url = cast(str, icon_app.get("icon_url"))
        require(bool(self.state.icon_url), "icon upload did not return an icon URL")

        screenshot_files = self._image_file()
        try:
            screenshot_response = self.admin.request(
                "POST",
                f"{API_PREFIX}/admin/apps/{self.state.app_id}/screenshots",
                expected=200,
                data={"position": "0"},
                files=screenshot_files,
            )
        finally:
            self._close_files(screenshot_files)
        screenshot_app = json_object(screenshot_response)
        screenshots = screenshot_app.get("screenshots")
        require(isinstance(screenshots, list) and len(screenshots) == 1, "screenshot upload failed")
        screenshots = cast(list[Any], screenshots)
        screenshot = cast(dict[str, Any], screenshots[0])
        self.state.screenshot_id = cast(str, screenshot.get("id"))
        self.state.screenshot_url = cast(str, screenshot.get("url"))
        require(
            screenshot.get("position") == 0 and self.state.screenshot_url, "screenshot metadata is invalid"
        )

        current = json_object(
            self.admin.request("GET", f"{API_PREFIX}/admin/apps/{self.state.app_id}", expected=200)
        )
        require(current.get("icon_url") == self.state.icon_url, "denied upload replaced the icon")

    def _apk_publish(self) -> None:
        require(self.state.app_id, "app id is missing")
        with self.config.apk_path.open("rb") as apk_file:
            upload = self.admin.request(
                "POST",
                f"{API_PREFIX}/admin/apps/{self.state.app_id}/versions",
                expected=201,
                data={"release_notes": f"{self.prefix} upload", "publish": "false"},
                files={
                    "file": (
                        self.config.apk_path.name,
                        apk_file,
                        "application/vnd.android.package-archive",
                    )
                },
            )
        version = json_object(upload)
        self.state.version_id = cast(str, version.get("id"))
        require(
            version.get("status") == "draft" and version.get("download_enabled") is False,
            "version is not draft",
        )
        require(version.get("file_size") == self.apk_size, "server APK size differs from fixture")
        require(version.get("sha256") == self.apk_sha256, "server APK digest differs from fixture")
        require(bool(version.get("signing_cert_sha256")), "server did not record the APK signer")
        published = json_object(
            self.admin.request(
                "POST",
                f"{API_PREFIX}/admin/apps/{self.state.app_id}/versions/{self.state.version_id}/publish",
                expected=200,
                json={"release_notes": f"{self.prefix} published and verified"},
            )
        )
        require(published.get("status") == "published", "version was not published")
        require(published.get("download_enabled") is True, "published version is not downloadable")

    def _catalog_scope(self) -> None:
        require(self.state.app_id and self.state.version_id, "published app state is incomplete")
        tester_apps = json_object_list(self.tester.request("GET", f"{API_PREFIX}/apps", expected=200))
        require(find_item(tester_apps, "id", self.state.app_id), "assigned tester cannot see published app")
        tester_detail = json_object(
            self.tester.request("GET", f"{API_PREFIX}/apps/{self.state.app_id}", expected=200)
        )
        current_version = tester_detail.get("current_version")
        require(isinstance(current_version, dict), "tester app detail has no current version")
        current_version = cast(dict[str, Any], current_version)
        require(current_version.get("id") == self.state.version_id, "tester sees the wrong version")
        require(tester_detail.get("versions") == [], "tester can see administrator version history")
        require(
            len(cast(list[Any], tester_detail.get("screenshots", []))) == 1,
            "tester cannot see screenshot metadata",
        )

        outsider_apps = json_object_list(self.outsider.request("GET", f"{API_PREFIX}/apps", expected=200))
        require(find_item(outsider_apps, "id", self.state.app_id) is None, "out-of-group user can see app")
        hidden = self.outsider.request("GET", f"{API_PREFIX}/apps/{self.state.app_id}", expected=404)
        assert_error_code(hidden, "app_not_found")
        denied_download = self.outsider.request(
            "POST",
            f"{API_PREFIX}/downloads",
            expected=404,
            json={"version_id": self.state.version_id, "client_request_id": str(uuid.uuid4())},
        )
        assert_error_code(denied_download, "download_unavailable")

        require(self.state.icon_url and self.state.screenshot_url, "media URLs are missing")
        media_urls = cast(tuple[str, str], (self.state.icon_url, self.state.screenshot_url))
        for media_url in media_urls:
            media = self.tester.request("GET", media_url, expected=200)
            require(media.headers.get("content-type", "").startswith("image/"), "media type is not image")
            require(media.content, "authorized media response is empty")
            require(
                "private" in media.headers.get("cache-control", ""), "private media is publicly cacheable"
            )
            denied_media = self.outsider.request("GET", media_url, expected=404)
            assert_error_code(denied_media, "file_not_found")

    def _download(self) -> None:
        require(self.state.version_id, "version id is missing")
        client_request_id = str(uuid.uuid4())
        request_payload = {
            "version_id": self.state.version_id,
            "client_request_id": client_request_id,
            "device_model": "Remote Acceptance Device",
            "android_version": "15",
            "client_version": self.prefix,
        }
        first = json_object(
            self.tester.request("POST", f"{API_PREFIX}/downloads", expected=201, json=request_payload)
        )
        self.redactor.add(first.get("ticket"))
        first_url = first.get("url")
        require(isinstance(first_url, str), "first download ticket response has no URL")
        second = json_object(
            self.tester.request("POST", f"{API_PREFIX}/downloads", expected=201, json=request_payload)
        )
        self.redactor.add(second.get("ticket"))
        require(first.get("download_id") == second.get("download_id"), "download idempotency changed id")
        require(first.get("ticket") != second.get("ticket"), "download ticket did not rotate")
        self.state.download_id = cast(str, second.get("download_id"))
        download_url = second.get("url")
        require(isinstance(download_url, str), "download ticket response has no URL")
        download_url = cast(str, download_url)
        require(second.get("file_size") == self.apk_size, "ticket APK size is incorrect")
        require(second.get("sha256") == self.apk_sha256, "ticket APK digest is incorrect")

        rotated = self.tester.request("GET", cast(str, first_url), expected=404)
        assert_error_code(rotated, "download_unavailable")
        anonymous = self.anonymous.request("GET", download_url, expected=404, auth=False)
        assert_error_code(anonymous, "download_unavailable")
        outsider = self.outsider.request("GET", download_url, expected=404, headers={"Range": "bytes=0-15"})
        assert_error_code(outsider, "download_unavailable")

        ranged = self.tester.request(
            "GET",
            download_url,
            expected=206,
            headers={"Range": "bytes=0-15"},
        )
        with self.config.apk_path.open("rb") as apk_source:
            first_bytes = apk_source.read(16)
        require(ranged.content == first_bytes, "Range response bytes differ from APK fixture")
        require(
            ranged.headers.get("content-type", "").startswith("application/vnd.android.package-archive"),
            "Range response has the wrong APK media type",
        )
        expected_range = f"bytes 0-15/{self.apk_size}"
        require(ranged.headers.get("content-range") == expected_range, "Content-Range is incorrect")
        require(ranged.headers.get("accept-ranges", "").lower() == "bytes", "Range support is missing")

        unsatisfied = self.tester.request(
            "GET",
            download_url,
            expected=416,
            headers={"Range": f"bytes={self.apk_size}-"},
        )
        require(
            unsatisfied.headers.get("content-range") == f"bytes */{self.apk_size}",
            "unsatisfied Range response has the wrong Content-Range",
        )

        transferred = self.tester.request("GET", download_url, expected=200)
        require(len(transferred.content) == self.apk_size, "downloaded APK size is incorrect")
        require(
            hashlib.sha256(transferred.content).hexdigest() == self.apk_sha256,
            "downloaded APK digest is incorrect",
        )
        require("no-store" in transferred.headers.get("cache-control", ""), "APK response is cacheable")
        require(
            "attachment" in transferred.headers.get("content-disposition", ""),
            "APK response is missing attachment disposition",
        )
        complete_payload = {"sha256": self.apk_sha256, "bytes_received": self.apk_size}
        completed = self.tester.request(
            "POST",
            f"{API_PREFIX}/downloads/{self.state.download_id}/complete",
            expected=204,
            json=complete_payload,
        )
        require(not completed.content, "download completion 204 response must be empty")
        repeated = self.tester.request(
            "POST",
            f"{API_PREFIX}/downloads/{self.state.download_id}/complete",
            expected=204,
            json=complete_payload,
        )
        require(not repeated.content, "idempotent completion response must be empty")
        consumed = self.tester.request("GET", download_url, expected=404)
        assert_error_code(consumed, "download_unavailable")

    def _bugs(self) -> None:
        require(self.state.app_id and self.state.version_id, "app/version state is missing")
        bug_files = self._image_file()
        try:
            created_response = self.tester.request(
                "POST",
                f"{API_PREFIX}/bugs",
                expected=201,
                data={
                    "app_id": self.state.app_id,
                    "version_id": self.state.version_id,
                    "title": f"{self.prefix} screenshot regression",
                    "description": f"{self.prefix} verified black-box Bug description",
                    "reproduction_steps": "Open the fixture and inspect the acceptance label",
                    "device_model": "Remote Acceptance Device",
                    "android_version": "15",
                    "client_version": self.prefix,
                    "visibility": "group",
                },
                files={"files": bug_files["file"]},
            )
        finally:
            self._close_files(bug_files)
        bug = json_object(created_response)
        self.state.bug_id = cast(str, bug.get("id"))
        require(
            bug.get("status") == "pending" and bug.get("reporter_id") == self.state.tester_id,
            "Bug reporter/state is wrong",
        )
        attachments = bug.get("attachments")
        require(isinstance(attachments, list) and len(attachments) == 1, "Bug attachment was not stored")
        attachments = cast(list[Any], attachments)
        attachment = cast(dict[str, Any], attachments[0])
        self.state.bug_attachment_url = cast(str, attachment.get("url"))
        require(bool(self.state.bug_attachment_url), "Bug attachment URL is missing")
        reporter_attachment = self.tester.request("GET", self.state.bug_attachment_url, expected=200)
        require(
            reporter_attachment.headers.get("content-type", "").startswith("image/"),
            "Bug evidence is not an image",
        )
        require(
            "no-store" in reporter_attachment.headers.get("cache-control", ""), "Bug evidence is cacheable"
        )

        tester_comment = f"{self.prefix} reporter comment"
        public_admin_comment = f"{self.prefix} administrator public comment"
        internal_admin_comment = f"{self.prefix} administrator internal note"
        self.tester.request(
            "POST",
            f"{API_PREFIX}/bugs/{self.state.bug_id}/comments",
            expected=200,
            json={"content": tester_comment},
        )
        self.admin.request(
            "POST",
            f"{API_PREFIX}/admin/bugs/{self.state.bug_id}/comments",
            expected=200,
            json={"content": public_admin_comment, "internal": False},
        )
        admin_bug = json_object(
            self.admin.request(
                "POST",
                f"{API_PREFIX}/admin/bugs/{self.state.bug_id}/comments",
                expected=200,
                json={"content": internal_admin_comment, "internal": True},
            )
        )
        admin_comments = cast(list[dict[str, Any]], admin_bug.get("comments", []))
        require(
            find_item(admin_comments, "content", internal_admin_comment), "admin cannot see internal note"
        )
        admin_attachment = self.admin.request("GET", self.state.bug_attachment_url, expected=200)
        require(admin_attachment.content, "admin cannot access Bug evidence")

        in_progress = json_object(
            self.admin.request(
                "PATCH",
                f"{API_PREFIX}/admin/bugs/{self.state.bug_id}/status",
                expected=200,
                json={"status": "in_progress", "note": f"{self.prefix} triaged"},
            )
        )
        require(in_progress.get("status") == "in_progress", "Bug did not enter in-progress state")
        verifying = json_object(
            self.admin.request(
                "PATCH",
                f"{API_PREFIX}/admin/bugs/{self.state.bug_id}/status",
                expected=200,
                json={
                    "status": "verifying",
                    "note": f"{self.prefix} ready for verification",
                    "fix_version_id": self.state.version_id,
                },
            )
        )
        require(verifying.get("status") == "verifying", "Bug did not enter verifying state")

        require(
            self.state.group_id and self.state.outsider_id and self.state.tester_id,
            "group/user state missing",
        )
        updated_group = json_object(
            self.admin.request(
                "PATCH",
                f"{API_PREFIX}/admin/groups/{self.state.group_id}",
                expected=200,
                json={"member_ids": [self.state.tester_id, self.state.outsider_id]},
            )
        )
        require(
            set(updated_group.get("member_ids", [])) == {self.state.tester_id, self.state.outsider_id},
            "group update failed",
        )
        peer_apps = json_object_list(self.outsider.request("GET", f"{API_PREFIX}/apps", expected=200))
        require(find_item(peer_apps, "id", self.state.app_id), "new group member cannot see app")
        peer_bug = json_object(
            self.outsider.request("GET", f"{API_PREFIX}/bugs/{self.state.bug_id}", expected=200)
        )
        for sensitive_key in (
            "reporter_id",
            "reporter_name",
            "description",
            "reproduction_steps",
            "device_model",
            "android_version",
            "client_version",
        ):
            require(peer_bug.get(sensitive_key) is None, f"peer can see sensitive Bug field {sensitive_key}")
        require(peer_bug.get("attachments") == [], "peer can see Bug evidence metadata")
        require(
            peer_bug.get("comments") == [] and peer_bug.get("transitions") == [], "peer can see Bug history"
        )
        peer_attachment = self.outsider.request("GET", self.state.bug_attachment_url, expected=404)
        assert_error_code(peer_attachment, "file_not_found")

        reporter_bug = json_object(
            self.tester.request("GET", f"{API_PREFIX}/bugs/{self.state.bug_id}", expected=200)
        )
        reporter_comments = cast(list[dict[str, Any]], reporter_bug.get("comments", []))
        require(find_item(reporter_comments, "content", tester_comment), "reporter comment is missing")
        require(
            find_item(reporter_comments, "content", public_admin_comment), "public admin comment is missing"
        )
        require(
            find_item(reporter_comments, "content", internal_admin_comment) is None, "internal note leaked"
        )
        verified = json_object(
            self.tester.request(
                "POST",
                f"{API_PREFIX}/bugs/{self.state.bug_id}/verification",
                expected=200,
                json={"accepted": True, "note": f"{self.prefix} verification passed"},
            )
        )
        require(verified.get("status") == "closed", "accepted verification did not close Bug")
        require(verified.get("resolution") == "fixed", "accepted verification resolution is not fixed")

    def _observability(self) -> None:
        require(
            self.state.app_id and self.state.version_id and self.state.download_id, "download state missing"
        )
        dashboard = json_object(self.admin.request("GET", f"{API_PREFIX}/admin/dashboard", expected=200))
        require(dashboard.get("active_apps", 0) >= 1, "dashboard does not count published app")
        require(dashboard.get("downloads_completed_7d", 0) >= 1, "dashboard does not count completion")
        downloads = page_items(
            self.admin.request(
                "GET",
                f"{API_PREFIX}/admin/downloads",
                expected=200,
                params={
                    "user_id": self.state.tester_id,
                    "app_id": self.state.app_id,
                    "version_id": self.state.version_id,
                    "status": "completed",
                    "page_size": 100,
                },
            )
        )
        record = find_item(downloads, "id", self.state.download_id)
        require(
            record is not None and record.get("bytes_sent") == self.apk_size, "download ledger is incorrect"
        )
        self._require_audit("admin.user.create", self.state.outsider_id)
        self._require_audit("admin.app.create", self.state.app_id)
        self._require_audit("admin.version.publish", self.state.version_id)
        self._require_audit("admin.bug.transition", self.state.bug_id, minimum=2)
        self._require_audit(
            "security.request_rejected",
            None,
            request_id=self.state.admin_rejection_id,
            exact=1,
        )
        self._require_audit(
            "security.request_rejected",
            None,
            request_id=self.state.anonymous_rejection_id,
            exact=0,
        )
        self._require_audit(
            "security.request_rejected",
            None,
            request_id=self.state.early_rejection_id,
            exact=0,
        )

    def _require_audit(
        self,
        action: str,
        entity_id: str | None,
        *,
        request_id: str | None = None,
        minimum: int = 1,
        exact: int | None = None,
    ) -> None:
        params: dict[str, object] = {"action": action, "page_size": 100}
        if entity_id:
            params["entity_id"] = entity_id
        if request_id:
            params["request_id"] = request_id
        payload = json_object(
            self.admin.request(
                "GET",
                f"{API_PREFIX}/admin/audit-logs",
                expected=200,
                params=params,
            )
        )
        total = payload.get("total")
        require(isinstance(total, int), "audit response has no total")
        total = cast(int, total)
        if exact is not None:
            require(total == exact, f"audit count for {action} is {total}, expected {exact}")
        else:
            require(total >= minimum, f"audit count for {action} is below {minimum}")

    def _cleanup(self) -> None:
        if self.state.app_id:
            archived = json_object(
                self.admin.request(
                    "PATCH",
                    f"{API_PREFIX}/admin/apps/{self.state.app_id}",
                    expected=200,
                    json={"status": "archived"},
                )
            )
            require(archived.get("status") == "archived", "acceptance app was not archived")
            tester_apps = json_object_list(self.tester.request("GET", f"{API_PREFIX}/apps", expected=200))
            require(find_item(tester_apps, "id", self.state.app_id) is None, "archived app remains visible")
        if self.state.group_id:
            group = json_object(
                self.admin.request(
                    "PATCH",
                    f"{API_PREFIX}/admin/groups/{self.state.group_id}",
                    expected=200,
                    json={"is_active": False},
                )
            )
            require(group.get("is_active") is False, "acceptance group was not deactivated")
        if self.state.outsider_id:
            user = json_object(
                self.admin.request(
                    "PATCH",
                    f"{API_PREFIX}/admin/users/{self.state.outsider_id}",
                    expected=200,
                    json={"is_active": False},
                )
            )
            require(user.get("is_active") is False, "acceptance user was not deactivated")
        self.state.cleanup_done = True

    def _best_effort_cleanup(self) -> None:
        if self.state.cleanup_done or not self.admin.access_token:
            return
        try:
            self._cleanup()
        except Exception as exc:  # cleanup must never hide the original acceptance failure
            print(f"WARN: best-effort cleanup failed: {self.redactor.redact(exc)}", file=sys.stderr)


def json_object_list(response: httpx.Response) -> list[dict[str, Any]]:
    try:
        payload = response.json()
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise AcceptanceError("response is not a JSON array") from exc
    require(isinstance(payload, list), "response JSON must be an array")
    require(all(isinstance(item, dict) for item in payload), "array items must be objects")
    return cast(list[dict[str, Any]], payload)


def run_self_test() -> None:
    password = "mock-password-value"
    token = "mock-token-value"
    ticket = "mock-ticket-value"
    redactor = Redactor((password, token, ticket))

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/ok":
            require(request.headers.get("authorization") == f"Bearer {token}", "mock auth missing")
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(
            500,
            json={"error": {"code": "mock_failure", "message": f"{password} {ticket}"}},
        )

    session = ApiSession(
        "https://mock.invalid",
        redactor,
        transport=httpx.MockTransport(handler),
    )
    session.access_token = token
    try:
        session.request("GET", "/ok", expected=200)
        try:
            session.request("GET", f"/fail?ticket={ticket}", expected=200)
        except AcceptanceError as exc:
            message = str(exc)
            require(
                password not in message and token not in message and ticket not in message, "secret leaked"
            )
            require("<redacted>" in message, "mock failure did not exercise redaction")
        else:
            raise AcceptanceError("MockTransport failure path did not fail")
    finally:
        session.close()

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    received: list[bytes] = []

    def serve_once() -> None:
        connection, _address = listener.accept()
        with connection:
            data = b""
            while b"\r\n\r\n" not in data:
                data += connection.recv(4096)
            received.append(data)
            connection.sendall(b"HTTP/1.1 401 Unauthorized\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
        listener.close()

    server_thread = threading.Thread(target=serve_once, daemon=True)
    server_thread.start()
    status = early_rejection_probe(
        f"http://127.0.0.1:{port}",
        endpoint=f"{API_PREFIX}/admin/apps/{uuid.uuid4()}/icon",
        request_id="mock-early-rejection",
        timeout=5,
        insecure=False,
        ca_file=None,
    )
    server_thread.join(timeout=5)
    require(status == 401, "mock early-rejection status is wrong")
    require(bool(received) and received[0].endswith(b"\r\n\r\n"), "probe sent an upload body")
    require(
        safe_url(f"https://example.invalid/file?ticket={ticket}").endswith("ticket=%3Credacted%3E"),
        "ticket URL is not sanitized",
    )
    with tempfile.TemporaryDirectory() as temporary_directory:
        temp_root = Path(temporary_directory)
        apk_path = temp_root / "fixture.apk"
        image_path = temp_root / "fixture.png"
        apk_path.write_bytes(b"PK" + b"\x00" * 62)
        image_path.write_bytes(b"\x89PNG\r\n\x1a\n")
        runner = AcceptanceRunner(
            Config(
                base_url="http://127.0.0.1:8080",
                admin_phone="+8613800000001",
                admin_password=password,
                tester_phone="+8613800000002",
                tester_password=password,
                apk_path=apk_path,
                image_path=image_path,
                apk_package=DEFAULT_APK_PACKAGE,
                timeout=5,
                insecure=False,
                ca_file=None,
            ),
            redactor,
        )
        require(runner.apk_size == 64 and runner.image_content_type == "image/png", "runner init failed")
        runner.close()
    print("self-test passed: MockTransport redaction and header-only rejection probe", flush=True)


def main(argv: list[str] | None = None) -> int:
    redactor = Redactor()
    try:
        parser = build_parser()
        args = parser.parse_args(argv)
        if args.self_test:
            run_self_test()
            return 0
        config = config_from_args(args)
        redactor.add(config.admin_password)
        redactor.add(config.tester_password)
        runner = AcceptanceRunner(config, redactor)
        runner.run()
        return 0
    except AcceptanceError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("FAIL: interrupted", file=sys.stderr)
        return 130
    except Exception as exc:  # keep unexpected failures concise; never emit a traceback with secrets
        print(
            redactor.redact(f"FAIL: unexpected {type(exc).__name__}: {exc}"),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
