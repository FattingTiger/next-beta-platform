from __future__ import annotations

import hashlib
import math
import os
import time
import uuid
from typing import Any, cast

from locust import HttpUser, between, task

_WAIT_MIN_ENV = "BETA_LOAD_WAIT_MIN_SECONDS"
_WAIT_MAX_ENV = "BETA_LOAD_WAIT_MAX_SECONDS"
_DEFAULT_WAIT_RANGE = (2.0, 5.0)


def _load_wait_range() -> tuple[float, float]:
    raw_minimum = os.environ.get(_WAIT_MIN_ENV)
    raw_maximum = os.environ.get(_WAIT_MAX_ENV)
    if raw_minimum is None and raw_maximum is None:
        return _DEFAULT_WAIT_RANGE
    if raw_minimum is None or raw_maximum is None:
        raise RuntimeError(f"{_WAIT_MIN_ENV} and {_WAIT_MAX_ENV} must be set together")
    try:
        minimum = float(raw_minimum)
        maximum = float(raw_maximum)
    except ValueError as exc:
        raise RuntimeError("load wait bounds must be finite numbers of seconds") from exc
    if not math.isfinite(minimum) or not math.isfinite(maximum):
        raise RuntimeError("load wait bounds must be finite numbers of seconds")
    if minimum < 0.1 or maximum > 60 or minimum > maximum:
        raise RuntimeError("load wait bounds must satisfy 0.1 <= minimum <= maximum <= 60 seconds")
    return minimum, maximum


class BetaCenterTester(HttpUser):
    """Read-heavy population profile with a small share of full downloads."""

    wait_time = between(*_load_wait_range())

    def on_start(self) -> None:
        token = os.environ.get("BETA_LOAD_ACCESS_TOKEN", "")
        phone = os.environ.get("BETA_LOAD_PHONE", "")
        password = os.environ.get("BETA_LOAD_PASSWORD", "")
        if not token and not (phone and password):
            raise RuntimeError("an access token or dedicated test-user credentials are required")
        self.refresh_token = ""
        if phone and password:
            response = self.client.post(
                "/api/v1/auth/login",
                json={"phone": phone, "password": password, "client_name": "mixed-load"},
                name="POST /api/v1/auth/login [mixed]",
            )
            if response.status_code != 200:
                raise RuntimeError(f"mixed load login failed with status {response.status_code}")
            try:
                login = cast(dict[str, Any], response.json())
                token = str(login["access_token"])
                self.refresh_token = str(login["refresh_token"])
            except (KeyError, TypeError, ValueError) as exc:
                raise RuntimeError("mixed load login returned invalid tokens") from exc
        self.headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        self.token_started = time.monotonic()
        self.app_id = os.environ.get("BETA_LOAD_APP_ID", "")
        self.version_id = os.environ.get("BETA_LOAD_VERSION_ID", "")
        if not self.app_id or not self.version_id:
            raise RuntimeError("BETA_LOAD_APP_ID and BETA_LOAD_VERSION_ID are required")
        self.max_file_bytes = int(os.environ.get("BETA_LOAD_MAX_FILE_BYTES", str(128 * 1024 * 1024)))
        if not 1024 * 1024 <= self.max_file_bytes <= 512 * 1024 * 1024:
            raise RuntimeError("BETA_LOAD_MAX_FILE_BYTES is outside the safe load range")

    @task(8)
    def list_apps(self) -> None:
        if not self._ensure_access():
            return
        self.client.get("/api/v1/apps", headers=self.headers, name="GET /api/v1/apps")

    @task(5)
    def app_detail(self) -> None:
        if self._ensure_access() and self.app_id:
            self.client.get(
                f"/api/v1/apps/{self.app_id}",
                headers=self.headers,
                name="GET /api/v1/apps/:id",
            )

    @task(5)
    def list_bugs(self) -> None:
        if not self._ensure_access():
            return
        self.client.get(
            "/api/v1/bugs?page=1&page_size=20",
            headers=self.headers,
            name="GET /api/v1/bugs",
        )

    @task(1)
    def download_lifecycle(self) -> None:
        if not self._ensure_access() or not self.version_id:
            return
        request_id = str(uuid.uuid4())
        with self.client.post(
            "/api/v1/downloads",
            headers=self.headers,
            json={"version_id": self.version_id, "client_request_id": request_id},
            name="POST /api/v1/downloads",
            catch_response=True,
        ) as started:
            if started.status_code != 201:
                started.failure(f"unexpected status {started.status_code}")
                return
            try:
                ticket = cast(dict[str, Any], started.json())
                file_size = int(ticket["file_size"])
                expected_sha256 = str(ticket["sha256"])
                download_id = str(ticket["download_id"])
                download_url = str(ticket["url"])
            except (KeyError, TypeError, ValueError) as exc:
                started.failure(f"invalid ticket response: {type(exc).__name__}")
                return
            if not 0 < file_size <= self.max_file_bytes:
                started.failure(f"file size {file_size} is outside the configured load range")
                return

        with self.client.get(
            download_url,
            headers=self.headers,
            name="GET /api/v1/downloads/:id/file",
            catch_response=True,
        ) as downloaded:
            if downloaded.status_code != 200:
                downloaded.failure(f"unexpected status {downloaded.status_code}")
                return
            digest = hashlib.sha256(downloaded.content).hexdigest()
            if len(downloaded.content) != file_size or digest != expected_sha256:
                downloaded.failure("download integrity mismatch")
                return

        with self.client.post(
            f"/api/v1/downloads/{download_id}/complete",
            headers=self.headers,
            json={"sha256": expected_sha256, "bytes_received": file_size},
            name="POST /api/v1/downloads/:id/complete",
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
            name="POST /api/v1/auth/refresh [mixed]",
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
