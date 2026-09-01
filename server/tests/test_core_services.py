from __future__ import annotations

import asyncio
import hashlib
import io
import os
import stat
import subprocess
import sys
import threading
import zipfile
from collections.abc import Iterable, Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated, cast

import pytest
from anyio import CapacityLimiter
from anyio.to_thread import current_default_thread_limiter, run_sync
from fastapi import Depends, FastAPI, UploadFile
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, SecretStr, ValidationError, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.datastructures import Headers

from beta_center import cli
from beta_center.config import DEVELOPMENT_SECRET_SENTINEL, Settings
from beta_center.database import Database, check_database
from beta_center.dependencies import Principal, get_db, require_ready_user
from beta_center.models import User, UserRole
from beta_center.runtime import Runtime
from beta_center.security import (
    LoginRateLimiter,
    decode_access_token,
    hash_password,
    normalize_phone,
    validate_password_strength,
    verify_password,
)
from beta_center.services.apk import ApkInspectionError, ApkInspector
from beta_center.services.storage import LocalStorage, StorageError


def make_upload(payload: bytes, content_type: str, filename: str = "upload.bin") -> UploadFile:
    return UploadFile(
        io.BytesIO(payload),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


def make_synthetic_apk(path: Path) -> bytes:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("AndroidManifest.xml", b"binary-manifest-placeholder")
        archive.writestr("classes.dex", b"dex\n035\x00synthetic")
    return path.read_bytes()


def assert_private_directory_mode(path: Path) -> None:
    metadata = path.stat()
    mode = stat.S_IMODE(metadata.st_mode)
    assert mode & 0o777 == 0o750
    if os.name != "posix":
        return
    process_groups = set(os.getgroups())
    if hasattr(os, "getegid"):
        process_groups.add(os.getegid())
    if getattr(os, "geteuid", lambda: -1)() == 0 or metadata.st_gid in process_groups:
        assert mode & stat.S_ISGID


def test_database_transactions_finish_before_responses_are_sent(context: object) -> None:
    """A client must be able to observe a successful write as soon as it gets the response."""

    def iter_routes(items: Iterable[object]) -> Iterator[object]:
        for item in items:
            included_router = getattr(item, "original_router", None)
            if included_router is not None:
                yield from iter_routes(included_router.routes)
            else:
                yield item

    def iter_dependencies(dependant: object) -> Iterator[object]:
        for dependency in getattr(dependant, "dependencies", []):
            yield dependency
            yield from iter_dependencies(dependency)

    routes_without_function_scope: list[str] = []
    database_dependency_count = 0
    app = context.app  # type: ignore[attr-defined]
    for route in iter_routes(app.routes):
        dependant = getattr(route, "dependant", None)
        if dependant is None:
            continue
        for dependency in iter_dependencies(dependant):
            if getattr(dependency, "call", None) is get_db:
                database_dependency_count += 1
                if getattr(dependency, "scope", None) != "function":
                    routes_without_function_scope.append(str(getattr(route, "path", "unknown")))

    assert database_dependency_count >= 49
    assert routes_without_function_scope == []


def test_authentication_releases_its_read_checkout_before_endpoint_work(context: object) -> None:
    """A burst must not hold DB connections across FastAPI thread-pool handoffs."""

    def transaction_probe(
        principal: Annotated[Principal, Depends(require_ready_user)],
        db: Annotated[Session, Depends(get_db, scope="function")],
    ) -> dict[str, object]:
        return {
            "user_id": principal.user.id,
            "transaction_active": db.in_transaction(),
        }

    app = context.app  # type: ignore[attr-defined]
    app.add_api_route("/_tests/auth-transaction", transaction_probe, methods=["GET"])
    auth = context.login(context.alice)  # type: ignore[attr-defined]
    response = context.client.get(  # type: ignore[attr-defined]
        "/_tests/auth-transaction",
        headers=auth.bearer,
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "user_id": context.alice.id,  # type: ignore[attr-defined]
        "transaction_active": False,
    }


def test_sync_worker_capacity_is_bounded_with_database_headroom(context: object) -> None:
    """Synchronous workers get bounded headroom beyond the DB connection count."""

    async def capacity_probe() -> dict[str, int]:
        return {
            "worker_tokens": int(current_default_thread_limiter().total_tokens),
            "database_tokens": int(
                context.runtime.database.request_limiter.total_tokens  # type: ignore[attr-defined]
            ),
        }

    app = context.app  # type: ignore[attr-defined]
    app.add_api_route("/_tests/thread-capacity", capacity_probe, methods=["GET"])
    response = context.client.get("/_tests/thread-capacity")  # type: ignore[attr-defined]

    expected = (
        context.runtime.settings.database_pool_size  # type: ignore[attr-defined]
        + context.runtime.settings.database_max_overflow  # type: ignore[attr-defined]
    ) * 2
    assert response.status_code == 200, response.text
    assert response.json() == {
        "worker_tokens": expected,
        "database_tokens": expected // 2,
    }


def test_database_capacity_covers_endpoint_and_response_validation() -> None:
    """A queued DB request must not consume a worker while an earlier response is validated."""

    response_validation_started = threading.Event()
    release_response_validation = threading.Event()
    second_endpoint_started = threading.Event()
    endpoint_calls = 0
    endpoint_lock = threading.Lock()
    session_events: list[str] = []

    class SessionProbe:
        def commit(self) -> None:
            session_events.append("commit")

        def rollback(self) -> None:
            session_events.append("rollback")

        def close(self) -> None:
            session_events.append("close")

    class ResponseProbe(BaseModel):
        value: str

        @field_validator("value")
        @classmethod
        def block_first_response_validation(cls, value: str) -> str:
            if not response_validation_started.is_set():
                response_validation_started.set()
                release_response_validation.wait(timeout=5)
            return value

    database_limiter = CapacityLimiter(1)
    runtime = cast(
        Runtime,
        SimpleNamespace(
            database=SimpleNamespace(
                request_limiter=database_limiter,
                session_factory=lambda: cast(Session, SessionProbe()),
            ),
        ),
    )

    def endpoint(
        _db: Annotated[Session, Depends(get_db, scope="function")],
    ) -> dict[str, str]:
        nonlocal endpoint_calls
        with endpoint_lock:
            endpoint_calls += 1
            if endpoint_calls == 2:
                second_endpoint_started.set()
        return {"value": "ok"}

    app = FastAPI()
    app.state.runtime = runtime
    app.add_api_route("/probe", endpoint, methods=["GET"], response_model=ResponseProbe)

    async def exercise() -> list[object]:
        requests: list[asyncio.Task[object]] = []
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://testserver",
            ) as client:
                requests.append(asyncio.create_task(client.get("/probe")))
                for _ in range(200):
                    if response_validation_started.is_set():
                        break
                    await asyncio.sleep(0.005)
                assert response_validation_started.is_set()
                assert database_limiter.borrowed_tokens == 1

                requests.append(asyncio.create_task(client.get("/probe")))
                for _ in range(200):
                    if database_limiter.statistics().tasks_waiting == 1:
                        break
                    await asyncio.sleep(0.005)

                assert database_limiter.statistics().tasks_waiting == 1
                assert not second_endpoint_started.is_set()
                release_response_validation.set()
                return list(await asyncio.wait_for(asyncio.gather(*requests), timeout=2))
        finally:
            release_response_validation.set()
            if requests:
                await asyncio.gather(*requests, return_exceptions=True)

    responses = asyncio.run(exercise())

    assert [response.status_code for response in responses] == [200, 200]  # type: ignore[attr-defined]
    assert endpoint_calls == 2
    assert session_events == ["commit", "close", "commit", "close"]
    assert database_limiter.available_tokens == 1


@pytest.mark.parametrize("endpoint_error", [False, True])
def test_database_finalizer_does_not_need_a_default_worker(endpoint_error: bool) -> None:
    """Session cleanup must finish while connection waiters occupy every worker."""

    events: list[str] = []

    class SessionProbe:
        def commit(self) -> None:
            events.append("commit")

        def rollback(self) -> None:
            events.append("rollback")

        def close(self) -> None:
            events.append("close")

    probe = SessionProbe()
    runtime = cast(
        Runtime,
        SimpleNamespace(
            database=SimpleNamespace(
                request_limiter=CapacityLimiter(1),
                session_factory=lambda: cast(Session, probe),
            ),
        ),
    )

    async def exercise() -> None:
        dependency = get_db(runtime)
        assert await anext(dependency) is probe

        # Model the synchronous endpoint phase, then let newer requests consume
        # every default worker while they wait for database connections.
        await run_sync(lambda: events.append("endpoint"))
        limiter = current_default_thread_limiter()
        previous_tokens = limiter.total_tokens
        limiter.total_tokens = 2
        release_workers = threading.Event()
        workers_started = [threading.Event(), threading.Event()]

        def occupy_worker(started: threading.Event) -> None:
            started.set()
            release_workers.wait(timeout=5)

        workers = [asyncio.create_task(run_sync(occupy_worker, started)) for started in workers_started]
        try:
            for _ in range(100):
                if all(started.is_set() for started in workers_started):
                    break
                await asyncio.sleep(0.005)
            assert all(started.is_set() for started in workers_started)

            if endpoint_error:
                with pytest.raises(RuntimeError, match="endpoint failed"):
                    await asyncio.wait_for(
                        dependency.athrow(RuntimeError("endpoint failed")),
                        timeout=0.25,
                    )
            else:
                with pytest.raises(StopAsyncIteration):
                    await asyncio.wait_for(anext(dependency), timeout=0.25)
        finally:
            release_workers.set()
            await asyncio.gather(*workers)
            limiter.total_tokens = previous_tokens

    asyncio.run(exercise())

    transaction_end = "rollback" if endpoint_error else "commit"
    assert events == ["endpoint", transaction_end, "close"]


def test_production_settings_reject_each_unsafe_default(tmp_path: Path) -> None:
    common = {
        "environment": "production",
        "database_url": f"sqlite:///{tmp_path / 'prod.sqlite3'}",
        "storage_root": tmp_path / "storage",
    }
    with pytest.raises(ValidationError, match="unique secret key"):
        Settings(**common)
    with pytest.raises(ValidationError, match="unique secret key"):
        Settings(**common, secret_key=SecretStr("short"), cookie_secure=True, auto_create_schema=False)
    with pytest.raises(ValidationError, match="secure cookies"):
        Settings(
            **common,
            secret_key=SecretStr("p" * 40),
            cookie_secure=False,
            auto_create_schema=False,
        )
    with pytest.raises(ValidationError, match="explicit database migrations"):
        Settings(
            **common,
            secret_key=SecretStr("p" * 40),
            cookie_secure=True,
            auto_create_schema=True,
        )

    hardened = {
        **common,
        "secret_key": SecretStr("p" * 40),
        "cookie_secure": True,
        "auto_create_schema": False,
        "public_base_url": "https://beta.example.test",
        "allowed_hosts": ["beta.example.test"],
    }
    with pytest.raises(ValidationError, match="PostgreSQL"):
        Settings(**hardened)
    with pytest.raises(ValidationError, match="must use HTTPS"):
        Settings(
            **{
                **hardened,
                "database_url": "postgresql+psycopg://beta@db/beta",
                "public_base_url": "http://beta.example.test",
            }
        )
    with pytest.raises(ValidationError, match="explicit allowed host"):
        Settings(
            **{
                **hardened,
                "database_url": "postgresql+psycopg://beta@db/beta",
                "allowed_hosts": ["*"],
            }
        )
    with pytest.raises(ValidationError, match="protected-file offload"):
        Settings(
            **{
                **hardened,
                "database_url": "postgresql+psycopg://beta@db/beta",
                "use_x_accel_redirect": False,
            }
        )

    valid = Settings(
        **{
            **hardened,
            "database_url": "postgresql+psycopg://beta@db/beta",
            "use_x_accel_redirect": True,
        }
    )
    assert valid.secret_key.get_secret_value() != DEVELOPMENT_SECRET_SENTINEL


def test_storage_rejects_traversal_invalid_names_types_empty_and_oversize(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path / "storage")
    for key in (
        "",
        "../outside.apk",
        str(tmp_path.parent / "outside.apk"),
        "nested/../../outside.apk",
    ):
        with pytest.raises(StorageError, match="非法文件路径"):
            storage.path_for(key)
    with pytest.raises(StorageError, match="非法存储命名空间"):
        storage._new_key("../bad", ".apk")

    with pytest.raises(StorageError, match="不支持的文件类型"):
        asyncio.run(
            storage.save_upload(
                make_upload(b"payload", "text/plain"),
                namespace="apks",
                extension="apk",
                max_bytes=100,
                expected_content_types={"application/octet-stream"},
            )
        )
    with pytest.raises(StorageError, match="不能为空"):
        asyncio.run(
            storage.save_upload(
                make_upload(b"", "application/octet-stream"),
                namespace="apks",
                extension="apk",
                max_bytes=100,
            )
        )
    with pytest.raises(StorageError, match="超过"):
        asyncio.run(
            storage.save_upload(
                make_upload(b"123456", "application/octet-stream"),
                namespace="apks",
                extension="apk",
                max_bytes=5,
            )
        )
    assert not any(path.suffix == ".part" for path in storage.root.rglob("*"))


def test_storage_upload_and_image_normalization_are_deterministic(
    tmp_path: Path,
    png_bytes: bytes,
) -> None:
    storage = LocalStorage(tmp_path / "storage")
    stored = asyncio.run(
        storage.save_upload(
            make_upload(b"verified-apk-bytes", "application/octet-stream", "app.apk"),
            namespace="apks",
            extension="apk",
            max_bytes=100,
        )
    )
    assert stored.key.startswith("apks/") and stored.key.endswith(".apk")
    assert stored.sha256 == hashlib.sha256(b"verified-apk-bytes").hexdigest()
    assert storage.exists(stored.key)
    stored_path = storage.path_for(stored.key)
    assert_private_directory_mode(storage.root)
    assert_private_directory_mode(stored_path.parent)
    assert stat.S_IMODE(stored_path.stat().st_mode) == 0o640
    storage.delete(stored.key)
    assert not storage.exists(stored.key)
    storage.delete(None)

    image = asyncio.run(
        storage.save_image(
            make_upload(png_bytes, "image/png", "screenshot.png"),
            namespace="bug-attachments",
            max_bytes=100_000,
            max_dimension=32,
        )
    )
    assert image.content_type == "image/webp"
    assert image.key.endswith(".webp")
    image_path = storage.path_for(image.key)
    assert image_path.read_bytes().startswith(b"RIFF")
    assert_private_directory_mode(image_path.parent)
    assert stat.S_IMODE(image_path.stat().st_mode) == 0o640

    for payload, content_type, message in (
        (b"data", "image/gif", "仅支持"),
        (b"", "image/png", "不能为空"),
        (png_bytes, "image/png", "超过"),
    ):
        with pytest.raises(StorageError, match=message):
            asyncio.run(
                storage.save_image(
                    make_upload(payload, content_type),
                    namespace="bug-attachments",
                    max_bytes=1 if payload else 100,
                )
            )


def test_apk_inspector_parses_only_authoritative_tool_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    apk_path = tmp_path / "valid.apk"
    payload = make_synthetic_apk(apk_path)
    inspector = ApkInspector(
        apksigner_path="test-apksigner",
        aapt_path="test-aapt",
        timeout_seconds=10,
        require_tools=True,
    )
    monkeypatch.setattr(inspector, "tools_available", lambda: True)
    certificate = ":".join(["AB"] * 32)

    def fake_run(command: list[str], _error: str) -> str:
        if command[0] == "test-apksigner":
            return f"Signer #1 certificate SHA-256 digest: {certificate}"
        return "\n".join(
            (
                "package: name='com.example.verified' versionCode='42' versionName='4.2.0'",
                "sdkVersion:'26'",
                "targetSdkVersion:'35'",
            )
        )

    monkeypatch.setattr(inspector, "_run", fake_run)
    result = inspector.inspect(apk_path)
    assert result.package_name == "com.example.verified"
    assert result.version_code == 42
    assert result.version_name == "4.2.0"
    assert result.min_sdk == 26
    assert result.target_sdk == 35
    assert result.signing_cert_sha256 == "ab" * 32
    assert result.sha256 == hashlib.sha256(payload).hexdigest()
    assert result.file_size == len(payload)


def test_apk_inspector_rejects_missing_tools_and_malformed_archives(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inspector = ApkInspector(
        apksigner_path="missing-apksigner",
        aapt_path="missing-aapt",
        timeout_seconds=10,
        require_tools=False,
    )
    valid_path = tmp_path / "valid.apk"
    make_synthetic_apk(valid_path)
    monkeypatch.setattr(inspector, "tools_available", lambda: False)
    with pytest.raises(ApkInspectionError, match="拒绝弱校验"):
        inspector.inspect(valid_path)

    wrong_extension = tmp_path / "valid.zip"
    wrong_extension.write_bytes(valid_path.read_bytes())
    with pytest.raises(ApkInspectionError, match="必须是 APK"):
        inspector._verify_zip(wrong_extension)
    corrupt = tmp_path / "corrupt.apk"
    corrupt.write_bytes(b"not-a-zip")
    with pytest.raises(ApkInspectionError, match="文件损坏"):
        inspector._verify_zip(corrupt)
    incomplete = tmp_path / "incomplete.apk"
    with zipfile.ZipFile(incomplete, "w") as archive:
        archive.writestr("AndroidManifest.xml", b"manifest")
    with pytest.raises(ApkInspectionError, match="有效的 Android APK"):
        inspector._verify_zip(incomplete)


def test_apk_tool_output_and_subprocess_failures_are_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    inspector = ApkInspector(
        apksigner_path="apksigner",
        aapt_path="aapt",
        timeout_seconds=10,
        require_tools=True,
    )
    with pytest.raises(ApkInspectionError, match="无法读取 APK 签名证书"):
        inspector._parse_certificate("no digest")
    with pytest.raises(ApkInspectionError, match="单一签名证书"):
        inspector._parse_certificate(
            f"certificate SHA-256 digest: {'a' * 64}\ncertificate SHA-256 digest: {'b' * 64}"
        )
    with pytest.raises(ApkInspectionError, match="摘要格式异常"):
        inspector._parse_certificate(f"certificate SHA-256 digest: {'a' * 66}")
    with pytest.raises(ApkInspectionError, match="无法读取 APK 包名"):
        inspector._parse_package("package output malformed")
    assert inspector._parse_optional_int("", "sdkVersion") is None

    def failed_signature(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        kwargs["stdout"].write(b"bad signature")  # type: ignore[union-attr]
        return subprocess.CompletedProcess(args[0], 1)

    monkeypatch.setattr(subprocess, "run", failed_signature)
    with pytest.raises(ApkInspectionError, match="bad signature"):
        inspector._run(["apksigner", "verify"], "APK 签名验证失败")

    def oversized_output(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        kwargs["stdout"].write(b"x" * (1024 * 1024 + 1))  # type: ignore[union-attr]
        return subprocess.CompletedProcess(args[0], 0)

    monkeypatch.setattr(subprocess, "run", oversized_output)
    with pytest.raises(ApkInspectionError, match="校验工具输出异常"):
        inspector._run(["aapt", "dump"], "APK 清单解析失败")

    def timeout(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired("apksigner", 10)

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(ApkInspectionError, match="APK 签名验证失败"):
        inspector._run(["apksigner", "verify"], "APK 签名验证失败")


def test_security_primitives_normalize_rate_limit_and_reject_tampering(context: object) -> None:
    assert normalize_phone(" +86 (138) 0000-0001 ") == "+8613800000001"
    with pytest.raises(ValueError, match="手机号格式"):
        normalize_phone("not-a-phone")
    for weak in ("short", "alllowercaseonly", "123456789012"):
        with pytest.raises(ValueError):
            validate_password_strength(weak)
    encoded = hash_password("Strong-Password-9!")
    assert verify_password("Strong-Password-9!", encoded) is True
    assert verify_password("Wrong-Password-9!", encoded) is False
    assert verify_password("anything", "not-an-argon-hash") is False

    limiter = LoginRateLimiter(window_seconds=10, max_per_ip=2, max_per_identity=1)
    assert limiter.check_and_record(request_ip="1.2.3.4", identity="alice", now_timestamp=100)
    assert not limiter.check_and_record(request_ip="1.2.3.4", identity="alice", now_timestamp=101)
    limiter.clear_identity("alice")
    assert limiter.check_and_record(request_ip="5.6.7.8", identity="alice", now_timestamp=102)
    assert limiter.check_and_record(request_ip="1.2.3.4", identity="bob", now_timestamp=111)

    with pytest.raises(ValueError):
        decode_access_token("tampered.jwt.value", context.runtime.settings)  # type: ignore[attr-defined]


def test_cli_bootstrap_and_doctor_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = Settings(
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'cli.sqlite3'}",
        storage_root=tmp_path / "storage",
        secret_key=SecretStr("cli-test-secret-key-with-at-least-32-characters"),
        require_apk_tools=False,
    )
    monkeypatch.setattr(cli, "Settings", lambda: settings)
    monkeypatch.setenv("BETA_BOOTSTRAP_PASSWORD", "Bootstrap-Password-8!")
    monkeypatch.setattr(
        sys,
        "argv",
        ["beta-center", "create-admin", "--phone", "+86 139 0000 0999", "--name", "首位管理员"],
    )
    cli.main()
    assert "Created administrator" in capsys.readouterr().out

    database = Database(settings)
    with database.session() as db:
        admin = db.scalar(select(User).where(User.phone == "+8613900000999"))
        assert admin is not None
        assert admin.role == UserRole.ADMIN
        assert admin.must_change_password is True
    check_database(database.engine)

    monkeypatch.setenv("BETA_BOOTSTRAP_PASSWORD", "Bootstrap-Password-8!")
    cli._create_admin(
        database,
        phone="+8613900000999",
        name="首位管理员",
        allow_existing=True,
    )
    assert "already exists" in capsys.readouterr().out
    monkeypatch.setenv("BETA_BOOTSTRAP_PASSWORD", "Bootstrap-Password-8!")
    with pytest.raises(SystemExit, match="already exists"):
        cli._create_admin(
            database,
            phone="+8613900000999",
            name="冲突账号",
            allow_existing=False,
        )
    database.dispose()

    monkeypatch.setattr(ApkInspector, "tools_available", lambda _self: True)
    monkeypatch.setattr(sys, "argv", ["beta-center", "doctor"])
    cli.main()
    doctor_output = capsys.readouterr().out
    assert "database: ok" in doctor_output
    assert "storage: ok" in doctor_output
    assert "apk tools: ok" in doctor_output


def test_doctor_exits_when_required_apk_tools_are_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = Settings(
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'doctor.sqlite3'}",
        storage_root=tmp_path / "storage",
        secret_key=SecretStr("doctor-secret-key-with-at-least-32-characters"),
        require_apk_tools=True,
    )
    database = Database(settings)
    database.create_schema()
    monkeypatch.setattr(ApkInspector, "tools_available", lambda _self: False)
    with pytest.raises(SystemExit) as exit_info:
        cli._doctor(settings, database)
    assert exit_info.value.code == 1
    assert "apk tools: missing" in capsys.readouterr().out
    database.dispose()
