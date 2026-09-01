from __future__ import annotations

import hashlib
import os
import time
import uuid
from typing import Any, cast

from locust import HttpUser, between, task
from requests import Response

_RANGE_ACCESS_TOKEN_ENV = "BETA_RANGE_ACCESS_TOKEN"
_FALLBACK_ACCESS_TOKEN_ENV = "BETA_LOAD_ACCESS_TOKEN"
_PHONE_ENV = "BETA_LOAD_PHONE"
_PASSWORD_ENV = "BETA_LOAD_PASSWORD"
_VERSION_ENV = "BETA_LOAD_VERSION_ID"
_CHUNK_BYTES_ENV = "BETA_RANGE_CHUNK_BYTES"
_MAX_FILE_BYTES_ENV = "BETA_RANGE_MAX_FILE_BYTES"
_DEFAULT_CHUNK_BYTES = 1024 * 1024
_DEFAULT_MAX_FILE_BYTES = 128 * 1024 * 1024


def _range_auth_inputs() -> tuple[str, str, str]:
    phone = os.environ.get(_PHONE_ENV, "").strip()
    password = os.environ.get(_PASSWORD_ENV, "")
    if bool(phone) != bool(password):
        raise RuntimeError(f"{_PHONE_ENV} and {_PASSWORD_ENV} must be set together")
    if phone and password:
        # Dedicated credentials deliberately take precedence for long runs so
        # every Locust user gets its own renewable session.
        return "", phone, password

    token = os.environ.get(_RANGE_ACCESS_TOKEN_ENV, "").strip()
    if not token:
        token = os.environ.get(_FALLBACK_ACCESS_TOKEN_ENV, "").strip()
    if not token:
        raise RuntimeError(
            f"set {_RANGE_ACCESS_TOKEN_ENV} (preferred), {_FALLBACK_ACCESS_TOKEN_ENV}, "
            f"or both {_PHONE_ENV} and {_PASSWORD_ENV}"
        )
    return token, "", ""


def _environment_int(name: str, default: int) -> int:
    raw_value = os.environ.get(name, str(default)).strip()
    try:
        return int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer number of bytes") from exc


def _range_parameters() -> tuple[str, int, int]:
    version_id = os.environ.get(_VERSION_ENV, "").strip()
    if not version_id:
        raise RuntimeError(f"{_VERSION_ENV} is required and cannot be blank")

    chunk_bytes = _environment_int(_CHUNK_BYTES_ENV, _DEFAULT_CHUNK_BYTES)
    max_file_bytes = _environment_int(_MAX_FILE_BYTES_ENV, _DEFAULT_MAX_FILE_BYTES)
    if not 64 * 1024 <= chunk_bytes <= 8 * 1024 * 1024:
        raise RuntimeError(f"{_CHUNK_BYTES_ENV} must be between 64 KiB and 8 MiB")
    if not chunk_bytes <= max_file_bytes <= 512 * 1024 * 1024:
        raise RuntimeError(
            f"{_MAX_FILE_BYTES_ENV} must be at least {_CHUNK_BYTES_ENV} and no more than 512 MiB"
        )
    return version_id, chunk_bytes, max_file_bytes


class BetaCenterRangeDownloader(HttpUser):
    """Reassemble an APK with bounded-memory Range requests and confirm its digest."""

    wait_time = between(0.5, 1.5)

    def on_start(self) -> None:
        token, phone, password = _range_auth_inputs()
        version_id, chunk_bytes, max_file_bytes = _range_parameters()
        self.refresh_token = ""
        if phone and password:
            response = self.client.post(
                "/api/v1/auth/login",
                json={"phone": phone, "password": password, "client_name": "range-load"},
                name="POST /api/v1/auth/login [range]",
            )
            if response.status_code != 200:
                raise RuntimeError(f"range load login failed with status {response.status_code}")
            try:
                login = cast(dict[str, Any], response.json())
                token = str(login["access_token"])
                self.refresh_token = str(login["refresh_token"])
            except (KeyError, TypeError, ValueError) as exc:
                raise RuntimeError("range load login returned invalid tokens") from exc
        self.headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        self.token_started = time.monotonic()
        self.version_id = version_id
        self.chunk_bytes = chunk_bytes
        self.max_file_bytes = max_file_bytes

    @task
    def range_download_lifecycle(self) -> None:
        if not self._ensure_access():
            return
        with self.client.post(
            "/api/v1/downloads",
            headers=self.headers,
            json={"version_id": self.version_id, "client_request_id": str(uuid.uuid4())},
            name="POST /api/v1/downloads [range]",
            catch_response=True,
        ) as started:
            if started.status_code != 201:
                started.failure(f"unexpected status {started.status_code}")
                return
            try:
                ticket = cast(dict[str, Any], started.json())
                file_size = int(ticket["file_size"])
                expected_sha256 = str(ticket["sha256"])
                download_url = str(ticket["url"])
                download_id = str(ticket["download_id"])
            except (KeyError, TypeError, ValueError) as exc:
                started.failure(f"invalid ticket response: {type(exc).__name__}")
                return
            if not 0 < file_size <= self.max_file_bytes:
                started.failure(f"file size {file_size} is outside the configured load range")
                return

        digest = hashlib.sha256()
        received_total = 0
        failed = False
        for offset in range(0, file_size, self.chunk_bytes):
            if not self._ensure_access():
                failed = True
                break
            last = min(offset + self.chunk_bytes, file_size) - 1
            with self.client.get(
                download_url,
                headers={**self.headers, "Range": f"bytes={offset}-{last}"},
                name="GET /api/v1/downloads/:id/file [range]",
                catch_response=True,
                stream=True,
            ) as response:
                if not self._accept_range(response, offset=offset, last=last, file_size=file_size):
                    failed = True
                    continue
                chunk_size = 0
                try:
                    for chunk in response.iter_content(chunk_size=64 * 1024):
                        if chunk:
                            chunk_size += len(chunk)
                            received_total += len(chunk)
                            digest.update(chunk)
                except OSError as exc:
                    response.failure(f"stream failed: {type(exc).__name__}")
                    failed = True
                    continue
                expected_size = last - offset + 1
                if chunk_size != expected_size:
                    response.failure(f"range body length {chunk_size} != {expected_size}")
                    failed = True

        if failed or received_total != file_size or digest.hexdigest() != expected_sha256:
            # A clean 204 here only means the server accepted the client's
            # failure report.  It must still be recorded as a failed Locust
            # lifecycle; otherwise a digest mismatch can disappear into a
            # successful aggregate row.
            with self.client.post(
                f"/api/v1/downloads/{download_id}/failure",
                headers=self.headers,
                json={"status": "failed", "reason": "range load integrity failure"},
                name="POST /api/v1/downloads/:id/failure [range]",
                catch_response=True,
            ) as ended:
                if ended.status_code == 204:
                    ended.failure("range download integrity mismatch")
                else:
                    ended.failure(f"failure report returned status {ended.status_code}")
            return

        with self.client.post(
            f"/api/v1/downloads/{download_id}/complete",
            headers=self.headers,
            json={"sha256": expected_sha256, "bytes_received": received_total},
            name="POST /api/v1/downloads/:id/complete [range]",
            catch_response=True,
        ) as completed:
            if completed.status_code != 204:
                completed.failure(f"unexpected status {completed.status_code}")

    def _ensure_access(self) -> bool:
        if not self.refresh_token or time.monotonic() - self.token_started < 12 * 60:
            return True
        with self.client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": self.refresh_token},
            name="POST /api/v1/auth/refresh [range]",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"refresh failed with status {response.status_code}")
                return False
            try:
                refreshed = cast(dict[str, Any], response.json())
                access_token = str(refreshed["access_token"])
                refresh_token = str(refreshed["refresh_token"])
            except (KeyError, TypeError, ValueError) as exc:
                response.failure(f"invalid refresh response: {type(exc).__name__}")
                return False
        self.headers["Authorization"] = f"Bearer {access_token}"
        self.refresh_token = refresh_token
        self.token_started = time.monotonic()
        return True

    @staticmethod
    def _accept_range(response: Response, *, offset: int, last: int, file_size: int) -> bool:
        if response.status_code != 206:
            response.failure(f"unexpected status {response.status_code}")  # type: ignore[attr-defined]
            return False
        expected = f"bytes {offset}-{last}/{file_size}"
        if response.headers.get("Content-Range") != expected:
            response.failure("incorrect Content-Range")  # type: ignore[attr-defined]
            return False
        if response.headers.get("Accept-Ranges", "").lower() != "bytes":
            response.failure("Accept-Ranges is missing")  # type: ignore[attr-defined]
            return False
        return True
