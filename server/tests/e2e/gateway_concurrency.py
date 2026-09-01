#!/usr/bin/env python3
"""Concurrent public-gateway acceptance checks with no successful uploads.

The test mixes catalog traffic, early admin-upload denials, and a valid tester's
full user-upload route. The full-chain probe sends only an invalid two-byte JSON
object, so it must pass user forward_auth and reach application validation as a
422 without creating a Bug or attachment. Admin probes never send their declared
multipart body.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import os
import random
import secrets
import socket
import ssl
import statistics
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast
from urllib.parse import urlsplit, urlunsplit

import httpx

Operation = Literal[
    "anonymous-admin-upload",
    "tester-admin-upload",
    "tester-bug-full-chain",
    "catalog",
]


class GateError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Config:
    base_url: str
    tester_token: str
    workers: int
    iterations: int
    timeout: float
    max_p95_ms: float
    insecure: bool
    ca_file: Path | None
    check_login_rate_limit: bool

    @property
    def verify(self) -> bool | str:
        if self.insecure:
            return False
        return str(self.ca_file) if self.ca_file else True


@dataclass(frozen=True, slots=True)
class Result:
    operation: Operation
    status_code: int
    elapsed_ms: float
    detail: str = ""


def require(condition: object, message: str) -> None:
    if not condition:
        raise GateError(message)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Exercise public forward_auth upload gates under bounded concurrency",
    )
    result.add_argument("--base-url", default=os.environ.get("BETA_GATE_BASE_URL"))
    result.add_argument("--tester-token", default=os.environ.get("BETA_GATE_TESTER_TOKEN"))
    result.add_argument("--workers", type=int, default=int(os.environ.get("BETA_GATE_WORKERS", "16")))
    result.add_argument("--iterations", type=int, default=int(os.environ.get("BETA_GATE_ITERATIONS", "10")))
    result.add_argument("--timeout", type=float, default=float(os.environ.get("BETA_GATE_TIMEOUT", "20")))
    result.add_argument(
        "--max-p95-ms", type=float, default=float(os.environ.get("BETA_GATE_MAX_P95_MS", "2000"))
    )
    result.add_argument("--ca-file", default=os.environ.get("BETA_GATE_CA_FILE"))
    result.add_argument(
        "--insecure",
        action="store_true",
        default=os.environ.get("BETA_GATE_INSECURE", "").lower() in {"1", "true", "yes"},
    )
    result.add_argument(
        "--check-login-rate-limit",
        action="store_true",
        help="last step: lock one random nonexistent identity after ten failed logins",
    )
    result.add_argument(
        "--confirm-public-test",
        action="store_true",
        help="required acknowledgement that this creates bounded public traffic",
    )
    result.add_argument("--self-test", action="store_true")
    return result


def config_from_args(args: argparse.Namespace) -> Config:
    require(args.confirm_public_test, "--confirm-public-test is required")
    require(args.base_url, "BETA_GATE_BASE_URL or --base-url is required")
    require(args.tester_token, "BETA_GATE_TESTER_TOKEN or --tester-token is required")
    parsed = urlsplit(str(args.base_url).strip())
    require(parsed.scheme == "https" and parsed.hostname, "the public gate test requires an HTTPS URL")
    require(not parsed.username and not parsed.password, "base URL must not contain credentials")
    require(not parsed.query and not parsed.fragment, "base URL must not contain query or fragment")
    require(1 <= args.workers <= 64, "workers must be between 1 and 64")
    require(1 <= args.iterations <= 100, "iterations must be between 1 and 100")
    require(3 <= args.timeout <= 120, "timeout must be between 3 and 120 seconds")
    require(100 <= args.max_p95_ms <= 30_000, "max P95 must be between 100 and 30000 ms")
    token = str(args.tester_token)
    require(len(token) >= 20 and not any(character.isspace() for character in token), "invalid tester token")
    ca_file = Path(str(args.ca_file)).expanduser().resolve() if args.ca_file else None
    require(not ca_file or ca_file.is_file(), "CA file does not exist")
    base_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))
    return Config(
        base_url=base_url,
        tester_token=token,
        workers=args.workers,
        iterations=args.iterations,
        timeout=args.timeout,
        max_p95_ms=args.max_p95_ms,
        insecure=bool(args.insecure),
        ca_file=ca_file,
        check_login_rate_limit=bool(args.check_login_rate_limit),
    )


def _read_status(connection: socket.socket | ssl.SSLSocket) -> int:
    received = b""
    while b"\r\n\r\n" not in received:
        chunk = connection.recv(4096)
        if not chunk:
            break
        received += chunk
        require(len(received) <= 64 * 1024, "upload gate returned oversized response headers")
    require(b"\r\n" in received, "upload gate closed without an HTTP response")
    status_line = received.split(b"\r\n", maxsplit=1)[0].decode("ascii", errors="replace")
    fields = status_line.split()
    require(len(fields) >= 2 and fields[0].startswith("HTTP/"), "upload gate returned invalid HTTP")
    try:
        return int(fields[1])
    except ValueError as exc:
        raise GateError("upload gate returned a nonnumeric status") from exc


def upload_probe(config: Config, *, authenticated: bool) -> int:
    parsed = urlsplit(config.base_url)
    require(parsed.hostname is not None, "base URL has no host")
    port = parsed.port or 443
    base_path = parsed.path.rstrip("/")
    target = f"{base_path}/api/v1/admin/apps/{uuid.uuid4()}/icon"
    boundary = f"beta-gate-{uuid.uuid4().hex}"
    auth_header = f"Authorization: Bearer {config.tester_token}\r\n" if authenticated else ""
    request = (
        f"POST {target} HTTP/1.1\r\n"
        f"Host: {parsed.netloc}\r\n"
        "User-Agent: beta-center-gateway-concurrency/1.0\r\n"
        f"X-Request-ID: gate-{uuid.uuid4().hex}\r\n"
        f"{auth_header}"
        f"Content-Type: multipart/form-data; boundary={boundary}\r\n"
        f"Content-Length: {8 * 1024 * 1024}\r\n"
        "Expect: 100-continue\r\n"
        "Connection: close\r\n\r\n"
    ).encode("ascii")
    raw_socket = socket.create_connection((parsed.hostname, port), timeout=config.timeout)
    connection: socket.socket | ssl.SSLSocket = raw_socket
    try:
        if config.insecure:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        else:
            context = ssl.create_default_context(cafile=str(config.ca_file) if config.ca_file else None)
        connection = context.wrap_socket(raw_socket, server_hostname=parsed.hostname)
        connection.settimeout(config.timeout)
        connection.sendall(request)
        return _read_status(connection)
    finally:
        connection.close()


def execute(operation: Operation, config: Config, client: httpx.Client) -> Result:
    started = time.monotonic()
    try:
        if operation == "anonymous-admin-upload":
            status = upload_probe(config, authenticated=False)
        elif operation == "tester-admin-upload":
            status = upload_probe(config, authenticated=True)
        elif operation == "tester-bug-full-chain":
            response = client.post(
                "/api/v1/bugs",
                headers={
                    "Authorization": f"Bearer {config.tester_token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "X-Request-ID": f"gate-full-{uuid.uuid4().hex}",
                },
                content=b"{}",
            )
            status = response.status_code
            if status == 422:
                require(error_code(response) == "validation_error", "Bug validation contract changed")
                require_api_headers(response, "Bug full-chain response")
        else:
            response = client.get(
                "/api/v1/apps",
                headers={"Authorization": f"Bearer {config.tester_token}", "Accept": "application/json"},
            )
            status = response.status_code
            if status == 200:
                require_api_headers(response, "catalog response")
        return Result(operation, status, (time.monotonic() - started) * 1000)
    except Exception as exc:
        return Result(operation, 0, (time.monotonic() - started) * 1000, type(exc).__name__)


def percentile(values: list[float], fraction: float) -> float:
    require(values, "cannot calculate a percentile for an empty result set")
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * fraction) - 1)
    return ordered[index]


def error_code(response: httpx.Response) -> str:
    try:
        body = response.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return ""
    if not isinstance(body, dict) or not isinstance(body.get("error"), dict):
        return ""
    value = cast(dict[str, object], body["error"]).get("code")
    return value if isinstance(value, str) else ""


def require_api_headers(response: httpx.Response, context: str) -> None:
    require(response.headers.get("x-content-type-options") == "nosniff", f"{context} lost nosniff")
    require(bool(response.headers.get("x-request-id")), f"{context} lost X-Request-ID")
    require("no-store" in response.headers.get("cache-control", ""), f"{context} is cacheable")


def check_login_rate_limit(config: Config, client: httpx.Client) -> None:
    # This identity is deliberately nonexistent. It avoids locking a real user,
    # but it consumes ten failures in the caller IP bucket for the configured
    # 15-minute window, so the check must run last.
    phone = f"+86197{secrets.randbelow(100_000_000):08d}"
    password = f"Gate-{secrets.token_urlsafe(18)}-A1!"
    for attempt in range(1, 12):
        response = client.post(
            "/api/v1/auth/login",
            json={"phone": phone, "password": password, "client_name": "gateway-rate-limit"},
        )
        if attempt <= 10:
            require(response.status_code == 401, f"failed login {attempt} returned {response.status_code}")
            require(error_code(response) == "invalid_credentials", "failed login error contract changed")
        else:
            require(response.status_code == 429, f"rate-limit request returned {response.status_code}")
            require(error_code(response) == "login_rate_limited", "login rate limit code is missing")
            retry_after = response.headers.get("retry-after", "")
            require(retry_after.isdigit() and int(retry_after) >= 60, "Retry-After is missing or invalid")
    print("rate-limit: 10 x 401 followed by 429 with Retry-After", flush=True)


def run(config: Config) -> None:
    each_count = config.workers * config.iterations
    operation_cycle: tuple[Operation, ...] = (
        "anonymous-admin-upload",
        "tester-admin-upload",
        "tester-bug-full-chain",
        "catalog",
    )
    operations = [operation for _ in range(each_count) for operation in operation_cycle]
    random.SystemRandom().shuffle(operations)
    with httpx.Client(
        base_url=config.base_url,
        verify=config.verify,
        timeout=httpx.Timeout(config.timeout, connect=min(config.timeout, 10)),
        follow_redirects=False,
        headers={"User-Agent": "beta-center-gateway-concurrency/1.0"},
    ) as client:
        with concurrent.futures.ThreadPoolExecutor(max_workers=config.workers) as executor:
            futures = [executor.submit(execute, operation, config, client) for operation in operations]
            results = [future.result() for future in concurrent.futures.as_completed(futures)]

        expected = {
            "anonymous-admin-upload": 401,
            "tester-admin-upload": 403,
            "tester-bug-full-chain": 422,
            "catalog": 200,
        }
        failures = [
            result for result in results if result.detail or result.status_code != expected[result.operation]
        ]
        for operation in cast(tuple[Operation, ...], tuple(expected)):
            timings = [result.elapsed_ms for result in results if result.operation == operation]
            p95 = percentile(timings, 0.95)
            mean = statistics.fmean(timings)
            print(
                f"{operation}: requests={len(timings)} mean_ms={mean:.1f} p95_ms={p95:.1f}",
                flush=True,
            )
            require(p95 <= config.max_p95_ms, f"{operation} P95 {p95:.1f}ms exceeds the gate")

        if failures:
            summary: dict[str, int] = {}
            for result in failures:
                key = f"{result.operation}:status={result.status_code}:error={result.detail or 'none'}"
                summary[key] = summary.get(key, 0) + 1
            raise GateError(f"wrong gate decisions: {summary}")
        print(f"gate concurrency: PASS ({len(results)} requests, zero wrong decisions)", flush=True)

        if config.check_login_rate_limit:
            check_login_rate_limit(config, client)


def self_test() -> None:
    require(percentile([1.0, 2.0, 3.0, 4.0, 100.0], 0.95) == 100.0, "P95 self-test failed")
    response = httpx.Response(
        429,
        json={"error": {"code": "login_rate_limited"}},
        headers={"Retry-After": "900"},
    )
    require(error_code(response) == "login_rate_limited", "error parser self-test failed")
    full_chain = httpx.Response(
        422,
        json={"error": {"code": "validation_error", "request_id": "gate-self-test"}},
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Request-ID": "gate-self-test",
        },
    )
    require(error_code(full_chain) == "validation_error", "full-chain parser self-test failed")
    require_api_headers(full_chain, "full-chain self-test")

    def mock_gateway(request: httpx.Request) -> httpx.Response:
        common_headers = {
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Request-ID": "gate-mock",
        }
        require(request.headers.get("authorization") == "Bearer tester-self-test-token", "mock lost auth")
        if request.url.path == "/api/v1/bugs":
            require(request.method == "POST" and request.content == b"{}", "full-chain body is not bounded")
            require(
                request.headers.get("content-type") == "application/json",
                "full-chain media type changed",
            )
            return httpx.Response(
                422,
                json={"error": {"code": "validation_error", "request_id": "gate-mock"}},
                headers=common_headers,
            )
        require(request.url.path == "/api/v1/apps" and request.method == "GET", "unexpected mock route")
        return httpx.Response(200, json=[], headers=common_headers)

    mock_config = Config(
        base_url="https://beta.example.test",
        tester_token="tester-self-test-token",
        workers=1,
        iterations=1,
        timeout=5,
        max_p95_ms=2000,
        insecure=False,
        ca_file=None,
        check_login_rate_limit=False,
    )
    with httpx.Client(
        base_url=mock_config.base_url,
        transport=httpx.MockTransport(mock_gateway),
    ) as mock_client:
        full_chain_result = execute("tester-bug-full-chain", mock_config, mock_client)
        catalog_result = execute("catalog", mock_config, mock_client)
    require(full_chain_result.status_code == 422 and not full_chain_result.detail, "full-chain mock failed")
    require(catalog_result.status_code == 200 and not catalog_result.detail, "catalog mock failed")
    print("gateway concurrency self-test: ok")


def main() -> int:
    args = parser().parse_args()
    if args.self_test:
        self_test()
        return 0
    run(config_from_args(args))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GateError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
