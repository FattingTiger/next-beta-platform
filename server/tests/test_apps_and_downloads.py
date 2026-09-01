from __future__ import annotations

import hashlib

from conftest import (
    TEST_CERTIFICATE,
    ApiContext,
    AuthTokens,
    FakeApkMetadata,
    PublishedApp,
)
from sqlalchemy import func, select

from beta_center.models import App, AppVersion, DownloadRecord, DownloadStatus, VersionStatus
from beta_center.services.apk import ApkInspectionError


def error_code(response: object) -> str:
    return response.json()["error"]["code"]  # type: ignore[attr-defined,no-any-return]


def test_published_app_visibility_tracks_active_group_membership(
    context: ApiContext,
    published_app: PublishedApp,
) -> None:
    assigned = context.client.get("/api/v1/apps", headers=published_app.alice_auth.bearer)
    assert assigned.status_code == 200
    assert [item["id"] for item in assigned.json()] == [published_app.app_id]
    assert assigned.json()[0]["current_version"]["version_code"] == 1

    detail = context.client.get(
        f"/api/v1/apps/{published_app.app_id}",
        headers=published_app.alice_auth.bearer,
    )
    assert detail.status_code == 200
    assert detail.json()["description"] == "仅面向指定内测组"
    assert detail.json()["versions"] == []
    assert detail.json()["current_version"]["id"] == published_app.version_id

    outsider_auth = context.login(context.outsider)
    outsider_list = context.client.get("/api/v1/apps", headers=outsider_auth.bearer)
    assert outsider_list.json() == []
    guessed = context.client.get(
        f"/api/v1/apps/{published_app.app_id}",
        headers=outsider_auth.bearer,
    )
    assert guessed.status_code == 404
    assert error_code(guessed) == "app_not_found"

    deactivated = context.client.patch(
        f"/api/v1/admin/groups/{published_app.group_id}",
        headers=published_app.admin_auth.bearer,
        json={"is_active": False},
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False
    assert context.client.get("/api/v1/apps", headers=published_app.alice_auth.bearer).json() == []
    revoked_detail = context.client.get(
        f"/api/v1/apps/{published_app.app_id}",
        headers=published_app.alice_auth.bearer,
    )
    assert revoked_detail.status_code == 404


def test_apk_upload_uses_inspector_metadata_and_publishes_atomically(context: ApiContext) -> None:
    admin = context.login(context.admin)
    group = context.create_group(admin, member_ids=[context.alice.id])
    app = context.create_app(admin, group_ids=[str(group["id"])])
    payload = b"not-an-apk-until-the-authoritative-fake-verifies-it"
    metadata = FakeApkMetadata(
        version_name="2.4.1",
        version_code=241,
        min_sdk=28,
        target_sdk=35,
    )

    version = context.upload_version(
        admin,
        str(app["id"]),
        metadata,
        payload=payload,
        publish=True,
    )
    expected_sha = hashlib.sha256(payload).hexdigest()
    assert version == {
        **version,
        "version_name": "2.4.1",
        "version_code": 241,
        "min_sdk": 28,
        "target_sdk": 35,
        "file_size": len(payload),
        "sha256": expected_sha,
        "signing_cert_sha256": TEST_CERTIFICATE,
        "release_notes": "版本 2.4.1",
        "status": "published",
        "download_enabled": True,
    }
    assert len(context.inspector.inspected_paths) == 2
    assert context.inspector.inspected_paths[0] == context.inspector.inspected_paths[1]

    with context.runtime.database.session() as db:
        stored_app = db.get(App, str(app["id"]))
        stored_version = db.get(AppVersion, str(version["id"]))
        assert stored_app is not None
        assert stored_version is not None
        assert stored_app.current_version_id == stored_version.id
        assert stored_app.signing_cert_sha256 == TEST_CERTIFICATE
        assert context.runtime.storage.path_for(stored_version.file_storage_key).read_bytes() == payload


def test_rejected_apk_inspection_never_creates_a_version_or_leaves_a_file(context: ApiContext) -> None:
    admin = context.login(context.admin)
    group = context.create_group(admin, member_ids=[context.alice.id])
    app = context.create_app(admin, group_ids=[str(group["id"])])
    before_files = list(context.runtime.storage.root.rglob("*"))
    context.inspector.queue(ApkInspectionError("APK 签名验证失败"))

    response = context.client.post(
        f"/api/v1/admin/apps/{app['id']}/versions",
        headers=admin.bearer,
        data={"release_notes": "不能发布", "publish": "false"},
        files={
            "file": (
                "untrusted.apk",
                b"untrusted-upload",
                "application/vnd.android.package-archive",
            )
        },
    )
    assert response.status_code == 422
    assert error_code(response) == "invalid_upload"
    assert "签名验证失败" in response.json()["error"]["message"]

    with context.runtime.database.session() as db:
        count = db.scalar(select(func.count(AppVersion.id)).where(AppVersion.app_id == app["id"]))
        assert count == 0
    assert [path for path in context.runtime.storage.root.rglob("*") if path.is_file()] == [
        path for path in before_files if path.is_file()
    ]


def test_package_version_code_and_signing_certificate_invariants(context: ApiContext) -> None:
    admin = context.login(context.admin)
    group = context.create_group(admin, member_ids=[context.alice.id])
    app = context.create_app(admin, group_ids=[str(group["id"])])
    first = context.upload_version(admin, str(app["id"]), FakeApkMetadata(), publish=True)

    cases = [
        (
            FakeApkMetadata(package_name="com.other.product", version_code=2, version_name="2.0"),
            "invalid_upload",
        ),
        (FakeApkMetadata(version_code=1, version_name="1.0.1"), "version_code_not_increasing"),
        (
            FakeApkMetadata(version_code=2, version_name="2.0", signing_cert_sha256="b" * 64),
            "signing_certificate_changed",
        ),
    ]
    for index, (metadata, expected_code) in enumerate(cases):
        context.inspector.queue(metadata)
        response = context.client.post(
            f"/api/v1/admin/apps/{app['id']}/versions",
            headers=admin.bearer,
            data={"release_notes": "拒绝", "publish": "false"},
            files={
                "file": (
                    f"rejected-{index}.apk",
                    f"payload-{index}".encode(),
                    "application/vnd.android.package-archive",
                )
            },
        )
        assert response.status_code in {409, 422}
        assert error_code(response) == expected_code

    second = context.upload_version(
        admin,
        str(app["id"]),
        FakeApkMetadata(version_code=2, version_name="2.0"),
        payload=b"synthetic-v2",
        publish=True,
    )
    with context.runtime.database.session() as db:
        old_version = db.get(AppVersion, str(first["id"]))
        new_version = db.get(AppVersion, str(second["id"]))
        assert old_version is not None and new_version is not None
        assert old_version.status == VersionStatus.PUBLISHED
        assert old_version.download_enabled is False
        assert new_version.status == VersionStatus.PUBLISHED
        assert new_version.download_enabled is True
        assert db.get(App, str(app["id"])).current_version_id == new_version.id  # type: ignore[union-attr]

    republish_old = context.client.post(
        f"/api/v1/admin/apps/{app['id']}/versions/{first['id']}/publish",
        headers=admin.bearer,
        json={"release_notes": "不允许重新发布旧版本"},
    )
    assert republish_old.status_code == 409
    assert error_code(republish_old) == "version_not_draft"


def test_upload_and_publish_are_separate_and_signing_anchor_is_set_only_on_publish(
    context: ApiContext,
) -> None:
    admin = context.login(context.admin)
    group = context.create_group(admin, member_ids=[context.alice.id])
    app = context.create_app(admin, group_ids=[str(group["id"])])
    payload = b"verified-but-not-yet-published"
    context.inspector.queue(FakeApkMetadata())
    combined = context.client.post(
        f"/api/v1/admin/apps/{app['id']}/versions",
        headers=admin.bearer,
        data={"release_notes": "禁止组合操作", "publish": "true"},
        files={
            "file": (
                "combined.apk",
                payload,
                "application/vnd.android.package-archive",
            )
        },
    )
    assert combined.status_code == 422
    assert error_code(combined) == "separate_publish_required"
    assert context.inspector.inspected_paths == []

    draft = context.upload_version(
        admin,
        str(app["id"]),
        FakeApkMetadata(),
        payload=payload,
        publish=False,
    )
    assert draft["status"] == "draft"
    with context.runtime.database.session() as db:
        stored_app = db.get(App, str(app["id"]))
        assert stored_app is not None
        assert stored_app.signing_cert_sha256 is None

    context.inspector.queue(FakeApkMetadata())
    published = context.client.post(
        f"/api/v1/admin/apps/{app['id']}/versions/{draft['id']}/publish",
        headers=admin.bearer,
        json={"release_notes": "独立发布"},
    )
    assert published.status_code == 200
    with context.runtime.database.session() as db:
        stored_app = db.get(App, str(app["id"]))
        assert stored_app is not None
        assert stored_app.signing_cert_sha256 == TEST_CERTIFICATE

    disabled = context.client.post(
        f"/api/v1/admin/apps/{app['id']}/versions/{draft['id']}/disable",
        headers=admin.bearer,
    )
    assert disabled.status_code == 200
    republish_disabled = context.client.post(
        f"/api/v1/admin/apps/{app['id']}/versions/{draft['id']}/publish",
        headers=admin.bearer,
        json={"release_notes": "停用后禁止重发"},
    )
    assert republish_disabled.status_code == 409
    assert error_code(republish_disabled) == "version_not_draft"


def start_download(context: ApiContext, app: PublishedApp, auth: AuthTokens | None = None):  # type: ignore[no-untyped-def]
    return context.client.post(
        "/api/v1/downloads",
        headers=(auth or app.alice_auth).bearer,
        json={
            "version_id": app.version_id,
            "device_model": "Pixel 9",
            "android_version": "16",
            "client_version": "1.0-test",
        },
    )


def test_download_client_request_id_retries_reuse_one_record_and_rotate_ticket(
    context: ApiContext,
    published_app: PublishedApp,
) -> None:
    client_request_id = "11111111-1111-4111-8111-111111111111"
    first = context.client.post(
        "/api/v1/downloads",
        headers=published_app.alice_auth.bearer,
        json={
            "version_id": published_app.version_id,
            "client_request_id": client_request_id,
            "device_model": "Pixel 9 first try",
        },
    )
    assert first.status_code == 201
    second = context.client.post(
        "/api/v1/downloads",
        headers=published_app.alice_auth.bearer,
        json={
            "version_id": published_app.version_id,
            "client_request_id": client_request_id,
            "device_model": "Pixel 9 retry",
        },
    )
    assert second.status_code == 201
    first_ticket = first.json()
    second_ticket = second.json()
    assert second_ticket["download_id"] == first_ticket["download_id"]
    assert second_ticket["client_request_id"] == client_request_id
    assert second_ticket["ticket"] != first_ticket["ticket"]

    with context.runtime.database.session() as db:
        records = list(
            db.scalars(
                select(DownloadRecord).where(
                    DownloadRecord.user_id == context.alice.id,
                    DownloadRecord.client_request_id == client_request_id,
                )
            )
        )
        assert len(records) == 1
        assert records[0].id == first_ticket["download_id"]
        assert records[0].device_model == "Pixel 9 retry"

    old_ticket = context.client.get(first_ticket["url"], headers=published_app.alice_auth.bearer)
    assert old_ticket.status_code == 404
    current_ticket = context.client.get(second_ticket["url"], headers=published_app.alice_auth.bearer)
    assert current_ticket.status_code == 200
    assert current_ticket.content == published_app.apk_payload


def test_download_client_request_id_conflicts_when_reused_for_another_version(
    context: ApiContext,
    published_app: PublishedApp,
) -> None:
    client_request_id = "22222222-2222-4222-8222-222222222222"
    first = context.client.post(
        "/api/v1/downloads",
        headers=published_app.alice_auth.bearer,
        json={"version_id": published_app.version_id, "client_request_id": client_request_id},
    )
    assert first.status_code == 201
    second_version = context.upload_version(
        published_app.admin_auth,
        published_app.app_id,
        FakeApkMetadata(version_code=2, version_name="2.0"),
        payload=b"synthetic-idempotency-v2",
        publish=True,
    )
    conflict = context.client.post(
        "/api/v1/downloads",
        headers=published_app.alice_auth.bearer,
        json={"version_id": second_version["id"], "client_request_id": client_request_id},
    )
    assert conflict.status_code == 409
    assert error_code(conflict) == "download_idempotency_conflict"
    with context.runtime.database.session() as db:
        records = list(
            db.scalars(
                select(DownloadRecord).where(
                    DownloadRecord.user_id == context.alice.id,
                    DownloadRecord.client_request_id == client_request_id,
                )
            )
        )
        assert len(records) == 1
        assert records[0].version_id == published_app.version_id


def test_download_ticket_is_hashed_scoped_and_requires_client_integrity_confirmation(
    context: ApiContext,
    published_app: PublishedApp,
) -> None:
    started = start_download(context, published_app)
    assert started.status_code == 201
    ticket = started.json()
    assert ticket["file_size"] == len(published_app.apk_payload)
    assert ticket["sha256"] == hashlib.sha256(published_app.apk_payload).hexdigest()
    assert ticket["ticket"] not in ticket["url"].split("ticket=", maxsplit=1)[0]

    with context.runtime.database.session() as db:
        record = db.get(DownloadRecord, ticket["download_id"])
        assert record is not None
        assert record.ticket_hash == hashlib.sha256(ticket["ticket"].encode()).hexdigest()
        assert record.ticket_hash != ticket["ticket"]
        assert record.status == DownloadStatus.STARTED

    wrong_ticket = context.client.get(
        f"/api/v1/downloads/{ticket['download_id']}/file",
        params={"ticket": "x" * 24},
        headers=published_app.alice_auth.bearer,
    )
    assert wrong_ticket.status_code == 404
    assert error_code(wrong_ticket) == "download_unavailable"

    downloaded = context.client.get(ticket["url"], headers=published_app.alice_auth.bearer)
    assert downloaded.status_code == 200
    assert downloaded.content == published_app.apk_payload
    assert downloaded.headers["content-type"] == "application/vnd.android.package-archive"
    assert downloaded.headers["cache-control"] == "private, no-store"
    assert downloaded.headers["x-content-type-options"] == "nosniff"

    other_user = context.client.post(
        f"/api/v1/downloads/{ticket['download_id']}/complete",
        headers=published_app.bob_auth.bearer,
        json={"sha256": ticket["sha256"], "bytes_received": ticket["file_size"]},
    )
    assert other_user.status_code == 404

    bad_integrity = context.client.post(
        f"/api/v1/downloads/{ticket['download_id']}/complete",
        headers=published_app.alice_auth.bearer,
        json={"sha256": "0" * 64, "bytes_received": ticket["file_size"]},
    )
    assert bad_integrity.status_code == 422
    assert error_code(bad_integrity) == "download_integrity_failed"

    completed = context.client.post(
        f"/api/v1/downloads/{ticket['download_id']}/complete",
        headers=published_app.alice_auth.bearer,
        json={"sha256": ticket["sha256"], "bytes_received": ticket["file_size"]},
    )
    assert completed.status_code == 204
    repeated = context.client.post(
        f"/api/v1/downloads/{ticket['download_id']}/complete",
        headers=published_app.alice_auth.bearer,
        json={"sha256": ticket["sha256"], "bytes_received": ticket["file_size"]},
    )
    assert repeated.status_code == 204
    assert context.client.get(ticket["url"], headers=published_app.alice_auth.bearer).status_code == 404

    with context.runtime.database.session() as db:
        record = db.get(DownloadRecord, ticket["download_id"])
        assert record is not None
        assert record.status == DownloadStatus.COMPLETED
        assert record.completed_at is not None
        assert record.bytes_sent == len(published_app.apk_payload)


def test_ticket_is_revoked_immediately_when_group_or_version_access_changes(
    context: ApiContext,
    published_app: PublishedApp,
) -> None:
    group_ticket = start_download(context, published_app).json()
    deactivated = context.client.patch(
        f"/api/v1/admin/groups/{published_app.group_id}",
        headers=published_app.admin_auth.bearer,
        json={"is_active": False},
    )
    assert deactivated.status_code == 200
    assert context.client.get(group_ticket["url"], headers=published_app.alice_auth.bearer).status_code == 404

    reactivated = context.client.patch(
        f"/api/v1/admin/groups/{published_app.group_id}",
        headers=published_app.admin_auth.bearer,
        json={"is_active": True},
    )
    assert reactivated.status_code == 200
    version_ticket = start_download(context, published_app).json()
    second = context.upload_version(
        published_app.admin_auth,
        published_app.app_id,
        FakeApkMetadata(version_code=2, version_name="2.0"),
        payload=b"synthetic-signed-apk-v2",
        publish=True,
    )
    assert second["download_enabled"] is True
    assert (
        context.client.get(version_ticket["url"], headers=published_app.alice_auth.bearer).status_code == 404
    )


def test_download_ticket_requires_same_current_authenticated_user(
    context: ApiContext,
    published_app: PublishedApp,
) -> None:
    ticket = start_download(context, published_app).json()
    context.client.cookies.clear()
    anonymous = context.client.get(ticket["url"])
    assert anonymous.status_code == 404
    assert error_code(anonymous) == "download_unavailable"

    another_user = context.client.get(ticket["url"], headers=published_app.bob_auth.bearer)
    assert another_user.status_code == 404
    assert error_code(another_user) == "download_unavailable"

    logout_all = context.client.post("/api/v1/auth/logout-all", headers=published_app.alice_auth.bearer)
    assert logout_all.status_code == 204
    revoked_session = context.client.get(ticket["url"], headers=published_app.alice_auth.bearer)
    assert revoked_session.status_code == 404
    assert error_code(revoked_session) == "download_unavailable"


def test_failed_download_can_retry_but_completed_download_cannot_be_relabelled(
    context: ApiContext,
    published_app: PublishedApp,
) -> None:
    ticket = start_download(context, published_app).json()
    failed = context.client.post(
        f"/api/v1/downloads/{ticket['download_id']}/failure",
        headers=published_app.alice_auth.bearer,
        json={"status": "failed", "reason": "网络连接中断"},
    )
    assert failed.status_code == 204
    assert context.client.get(ticket["url"], headers=published_app.alice_auth.bearer).status_code == 200
    completed = context.client.post(
        f"/api/v1/downloads/{ticket['download_id']}/complete",
        headers=published_app.alice_auth.bearer,
        json={"sha256": ticket["sha256"], "bytes_received": ticket["file_size"]},
    )
    assert completed.status_code == 204
    relabel = context.client.post(
        f"/api/v1/downloads/{ticket['download_id']}/failure",
        headers=published_app.alice_auth.bearer,
        json={"status": "cancelled", "reason": "不应覆盖完成状态"},
    )
    assert relabel.status_code == 409
    assert error_code(relabel) == "download_already_completed"


def test_missing_apk_file_returns_service_error_without_marking_complete(
    context: ApiContext,
    published_app: PublishedApp,
) -> None:
    ticket = start_download(context, published_app).json()
    with context.runtime.database.session() as db:
        version = db.get(AppVersion, published_app.version_id)
        assert version is not None
        apk_path = context.runtime.storage.path_for(version.file_storage_key)
    apk_path.unlink()

    response = context.client.get(ticket["url"], headers=published_app.alice_auth.bearer)
    assert response.status_code == 503
    assert error_code(response) == "apk_missing"
    with context.runtime.database.session() as db:
        record = db.get(DownloadRecord, ticket["download_id"])
        assert record is not None
        assert record.status == DownloadStatus.STARTED
        assert record.completed_at is None
