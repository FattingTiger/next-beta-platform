from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Self

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import SecretStr

from beta_center.config import Settings
from beta_center.database import Database
from beta_center.main import create_app
from beta_center.models import User, UserRole
from beta_center.runtime import Runtime
from beta_center.security import LoginRateLimiter, hash_password
from beta_center.services.apk import ApkInspection, ApkInspectionError
from beta_center.services.storage import LocalStorage

DEFAULT_PASSWORD = "Test-Password-9!"
FORCED_PASSWORD = "Initial-Password-7!"
NEW_PASSWORD = "Changed-Password-8!"
TEST_CERTIFICATE = "a" * 64


@dataclass(frozen=True, slots=True)
class SeedUser:
    id: str
    phone: str
    display_name: str
    password: str


@dataclass(frozen=True, slots=True)
class AuthTokens:
    access_token: str
    refresh_token: str
    csrf_token: str

    @property
    def bearer(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}


@dataclass(frozen=True, slots=True)
class FakeApkMetadata:
    package_name: str = "com.example.beta"
    version_name: str = "1.0.0"
    version_code: int = 1
    min_sdk: int | None = 26
    target_sdk: int | None = 35
    signing_cert_sha256: str = TEST_CERTIFICATE


class FakeApkInspector:
    """A deterministic stand-in for the authoritative external APK tools.

    Tests explicitly queue either verified metadata or an inspection failure. The
    application still has to call the inspector; this fixture never falls back to
    parsing unverified request fields.
    """

    def __init__(self) -> None:
        self._outcomes: list[FakeApkMetadata | Exception] = []
        self.inspected_paths: list[Path] = []

    def queue(self, outcome: FakeApkMetadata | Exception) -> Self:
        self._outcomes.append(outcome)
        return self

    def tools_available(self) -> bool:
        return True

    def inspect(self, path: Path) -> ApkInspection:
        self.inspected_paths.append(path)
        if not self._outcomes:
            raise ApkInspectionError("测试未配置可信 APK 检查结果")
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        payload = path.read_bytes()
        return ApkInspection(
            package_name=outcome.package_name,
            version_name=outcome.version_name,
            version_code=outcome.version_code,
            min_sdk=outcome.min_sdk,
            target_sdk=outcome.target_sdk,
            signing_cert_sha256=outcome.signing_cert_sha256,
            sha256=hashlib.sha256(payload).hexdigest(),
            file_size=len(payload),
        )


@dataclass(slots=True)
class ApiContext:
    client: TestClient
    runtime: Runtime
    inspector: FakeApkInspector
    app: object
    admin: SeedUser
    alice: SeedUser
    bob: SeedUser
    outsider: SeedUser
    forced: SeedUser

    def login(self, user: SeedUser, password: str | None = None) -> AuthTokens:
        response = self.client.post(
            "/api/v1/auth/login",
            json={"phone": user.phone, "password": password or user.password, "client_name": "pytest"},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        return AuthTokens(
            access_token=payload["access_token"],
            refresh_token=payload["refresh_token"],
            csrf_token=payload["csrf_token"],
        )

    def create_group(
        self,
        admin_auth: AuthTokens,
        *,
        name: str = "核心测试组",
        member_ids: list[str] | None = None,
        app_ids: list[str] | None = None,
    ) -> dict[str, object]:
        response = self.client.post(
            "/api/v1/admin/groups",
            headers=admin_auth.bearer,
            json={
                "name": name,
                "description": "自动化集成测试",
                "member_ids": member_ids or [],
                "app_ids": app_ids or [],
            },
        )
        assert response.status_code == 201, response.text
        return response.json()

    def create_app(
        self,
        admin_auth: AuthTokens,
        *,
        group_ids: list[str],
        package_name: str = "com.example.beta",
        name: str = "协作台",
    ) -> dict[str, object]:
        response = self.client.post(
            "/api/v1/admin/apps",
            headers=admin_auth.bearer,
            json={
                "name": name,
                "package_name": package_name,
                "short_description": "内部协作应用",
                "description": "仅面向指定内测组",
                "group_ids": group_ids,
            },
        )
        assert response.status_code == 201, response.text
        return response.json()

    def upload_version(
        self,
        admin_auth: AuthTokens,
        app_id: str,
        metadata: FakeApkMetadata,
        *,
        payload: bytes = b"synthetic-signed-apk-v1",
        publish: bool = True,
        filename: str = "collaboration.apk",
    ) -> dict[str, object]:
        self.inspector.queue(metadata)
        response = self.client.post(
            f"/api/v1/admin/apps/{app_id}/versions",
            headers=admin_auth.bearer,
            data={"release_notes": f"版本 {metadata.version_name}", "publish": "false"},
            files={"file": (filename, payload, "application/vnd.android.package-archive")},
        )
        assert response.status_code == 201, response.text
        version = response.json()
        if not publish:
            return version
        self.inspector.queue(metadata)
        published = self.client.post(
            f"/api/v1/admin/apps/{app_id}/versions/{version['id']}/publish",
            headers=admin_auth.bearer,
            json={"release_notes": f"版本 {metadata.version_name}"},
        )
        assert published.status_code == 200, published.text
        return published.json()


@dataclass(frozen=True, slots=True)
class PublishedApp:
    admin_auth: AuthTokens
    alice_auth: AuthTokens
    bob_auth: AuthTokens
    group_id: str
    app_id: str
    version_id: str
    apk_payload: bytes
    version: dict[str, object]


@pytest.fixture
def context(tmp_path: Path) -> ApiContext:
    settings = Settings(
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'test.sqlite3'}",
        storage_root=tmp_path / "storage",
        secret_key=SecretStr("pytest-only-secret-key-with-at-least-32-characters"),
        allowed_hosts=["testserver", "localhost"],
        login_failure_limit=3,
        login_lock_minutes=2,
        require_apk_tools=False,
        auto_create_schema=True,
    )
    database = Database(settings)
    inspector = FakeApkInspector()
    runtime = Runtime(
        settings=settings,
        database=database,
        storage=LocalStorage(settings.storage_root),
        apk_inspector=inspector,  # type: ignore[arg-type]
        login_limiter=LoginRateLimiter(max_per_ip=100, max_per_identity=100),
    )
    app = create_app(settings, runtime=runtime)
    with TestClient(app, raise_server_exceptions=False) as client:
        ready_hash = hash_password(DEFAULT_PASSWORD)
        forced_hash = hash_password(FORCED_PASSWORD)
        with database.session() as db:
            users = [
                User(
                    phone="+8613800000001",
                    display_name="系统管理员",
                    password_hash=ready_hash,
                    role=UserRole.ADMIN,
                    must_change_password=False,
                ),
                User(
                    phone="+8613800000002",
                    display_name="测试用户 Alice",
                    password_hash=ready_hash,
                    role=UserRole.TESTER,
                    must_change_password=False,
                ),
                User(
                    phone="+8613800000003",
                    display_name="测试用户 Bob",
                    password_hash=ready_hash,
                    role=UserRole.TESTER,
                    must_change_password=False,
                ),
                User(
                    phone="+8613800000004",
                    display_name="无关用户",
                    password_hash=ready_hash,
                    role=UserRole.TESTER,
                    must_change_password=False,
                ),
                User(
                    phone="+8613800000005",
                    display_name="首次登录用户",
                    password_hash=forced_hash,
                    role=UserRole.TESTER,
                    must_change_password=True,
                ),
            ]
            db.add_all(users)
            db.flush()
            identities = [
                SeedUser(users[0].id, users[0].phone, users[0].display_name, DEFAULT_PASSWORD),
                SeedUser(users[1].id, users[1].phone, users[1].display_name, DEFAULT_PASSWORD),
                SeedUser(users[2].id, users[2].phone, users[2].display_name, DEFAULT_PASSWORD),
                SeedUser(users[3].id, users[3].phone, users[3].display_name, DEFAULT_PASSWORD),
                SeedUser(users[4].id, users[4].phone, users[4].display_name, FORCED_PASSWORD),
            ]
        yield ApiContext(
            client=client,
            runtime=runtime,
            inspector=inspector,
            app=app,
            admin=identities[0],
            alice=identities[1],
            bob=identities[2],
            outsider=identities[3],
            forced=identities[4],
        )


@pytest.fixture
def published_app(context: ApiContext) -> PublishedApp:
    admin_auth = context.login(context.admin)
    alice_auth = context.login(context.alice)
    bob_auth = context.login(context.bob)
    group = context.create_group(
        admin_auth,
        member_ids=[context.alice.id, context.bob.id],
    )
    app = context.create_app(admin_auth, group_ids=[str(group["id"])])
    apk_payload = b"synthetic-signed-apk-v1"
    version = context.upload_version(
        admin_auth,
        str(app["id"]),
        FakeApkMetadata(),
        payload=apk_payload,
    )
    return PublishedApp(
        admin_auth=admin_auth,
        alice_auth=alice_auth,
        bob_auth=bob_auth,
        group_id=str(group["id"]),
        app_id=str(app["id"]),
        version_id=str(version["id"]),
        apk_payload=apk_payload,
        version=version,
    )


@pytest.fixture
def png_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (48, 80), color=(42, 86, 173)).save(output, format="PNG")
    return output.getvalue()
