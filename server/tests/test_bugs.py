from __future__ import annotations

from collections.abc import Callable
from unittest.mock import MagicMock

import pytest
from conftest import ApiContext, PublishedApp
from sqlalchemy import event, func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from beta_center.models import Bug, BugAttachment, BugComment
from beta_center.routers import admin_bugs as admin_bug_routes
from beta_center.routers import bugs as bug_routes


def error_code(response: object) -> str:
    return response.json()["error"]["code"]  # type: ignore[attr-defined,no-any-return]


def create_bug(
    context: ApiContext,
    app: PublishedApp,
    *,
    visibility: str = "group",
    png_bytes: bytes | None = None,
    title: str = "启动后列表内容发生错位",
):
    files = []
    if png_bytes is not None:
        files.append(("files", ("evidence.png", png_bytes, "image/png")))
    return context.client.post(
        "/api/v1/bugs",
        headers=app.alice_auth.bearer,
        data={
            "app_id": app.app_id,
            "version_id": app.version_id,
            "title": title,
            "description": "进入首页后快速滚动，第三张卡片会覆盖第二张卡片。",
            "reproduction_steps": "登录；进入首页；快速向下滚动。",
            "device_model": "Pixel 9",
            "android_version": "16",
            "client_version": "1.0-test",
            "visibility": visibility,
        },
        files=files,
    )


@pytest.mark.parametrize("get_bug", [bug_routes._get_bug, admin_bug_routes._get_bug])
def test_locked_bug_queries_target_only_bug_table_on_postgresql(
    get_bug: Callable[..., Bug],
) -> None:
    db = MagicMock(spec=Session)
    expected = MagicMock(spec=Bug)
    db.scalar.return_value = expected

    assert get_bug(db, "bug-id", lock=True) is expected
    statement = db.scalar.call_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))

    assert " FOR UPDATE OF bugs" in sql


def test_reporter_locked_bug_query_keeps_outer_joins_out_of_lock_scope() -> None:
    db = MagicMock(spec=Session)
    db.scalar.return_value = MagicMock(spec=Bug)

    bug_routes._get_bug(db, "bug-id", lock=True)
    statement = db.scalar.call_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))

    assert "LEFT OUTER JOIN" in sql
    assert sql.endswith("FOR UPDATE OF bugs")


def test_reporter_can_submit_atomic_bug_with_private_screenshot(
    context: ApiContext,
    published_app: PublishedApp,
    png_bytes: bytes,
) -> None:
    response = create_bug(context, published_app, png_bytes=png_bytes)
    assert response.status_code == 201, response.text
    bug = response.json()
    assert bug["reference"].startswith("BT-")
    assert bug["status"] == "pending"
    assert bug["reporter_id"] == context.alice.id
    assert bug["attachments"][0]["content_type"] == "image/webp"
    assert bug["transitions"][0]["from_status"] is None
    assert bug["transitions"][0]["to_status"] == "pending"

    attachment = context.client.get(
        bug["attachments"][0]["url"],
        headers=published_app.alice_auth.bearer,
    )
    assert attachment.status_code == 200
    assert attachment.headers["content-type"] == "image/webp"
    assert attachment.headers["cache-control"] == "private, no-store"
    assert attachment.content.startswith(b"RIFF")

    with context.runtime.database.session() as db:
        stored_bug = db.get(Bug, bug["id"])
        stored_attachment = db.scalar(select(BugAttachment).where(BugAttachment.bug_id == bug["id"]))
        assert stored_bug is not None and stored_attachment is not None
        path = context.runtime.storage.path_for(stored_attachment.storage_key)
        assert path.is_file()
        assert path.read_bytes() == attachment.content


def test_group_bug_redacts_reporter_identity_for_peer(
    context: ApiContext,
    published_app: PublishedApp,
) -> None:
    created = create_bug(context, published_app)
    assert created.status_code == 201
    bug_id = created.json()["id"]

    peer = context.client.get(
        f"/api/v1/bugs/{bug_id}",
        headers=published_app.bob_auth.bearer,
    )
    assert peer.status_code == 200
    payload = peer.json()
    assert payload["title"] == "启动后列表内容发生错位"
    for hidden_field in (
        "reporter_id",
        "reporter_name",
        "description",
        "reproduction_steps",
        "device_model",
        "android_version",
        "client_version",
    ):
        assert hidden_field not in payload
    assert payload["comments"] == []
    assert payload["transitions"] == []


def test_bug_list_preserves_full_reporter_payload_with_bounded_query_fanout(
    context: ApiContext,
    published_app: PublishedApp,
    png_bytes: bytes,
) -> None:
    created = create_bug(context, published_app, png_bytes=png_bytes)
    assert created.status_code == 201
    bug_id = created.json()["id"]
    commented = context.client.post(
        f"/api/v1/admin/bugs/{bug_id}/comments",
        headers=published_app.admin_auth.bearer,
        json={"content": "公开处理进度", "internal": False},
    )
    assert commented.status_code == 200
    # The same app can be visible through multiple groups. The access subquery
    # may yield duplicate IDs, but IN membership and Bug totals must not.
    context.create_group(
        published_app.admin_auth,
        name="第二性能回归组",
        member_ids=[context.alice.id],
        app_ids=[published_app.app_id],
    )

    statements: list[str] = []

    def capture_selects(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    engine = context.runtime.database.engine
    event.listen(engine, "before_cursor_execute", capture_selects)
    try:
        listing = context.client.get(
            "/api/v1/bugs?page=1&page_size=20",
            headers=published_app.alice_auth.bearer,
        )
    finally:
        event.remove(engine, "before_cursor_execute", capture_selects)

    assert listing.status_code == 200
    payload = listing.json()
    assert payload["total"] == 1
    item = payload["items"][0]
    assert item["id"] == bug_id
    assert item["description"]
    assert len(item["attachments"]) == 1
    assert [comment["content"] for comment in item["comments"]] == ["公开处理进度"]
    assert [transition["to_status"] for transition in item["transitions"]] == ["pending"]

    # Authentication reads plus one windowed Bug page and three batched
    # collection reads. This guards against restoring the former fixed fanout
    # of separate count/app/version/reporter/author/actor SELECTs.
    assert len(statements) <= 8, "\n\n".join(statements)
    windowed_pages = [statement for statement in statements if "count(bugs.id) over" in statement.lower()]
    assert len(windowed_pages) == 1

    past_end = context.client.get(
        "/api/v1/bugs?page=2&page_size=1",
        headers=published_app.alice_auth.bearer,
    )
    assert past_end.status_code == 200
    assert past_end.json() == {"items": [], "total": 1, "page": 2, "page_size": 1}


def test_bug_screenshot_is_only_visible_to_reporter_and_admin(
    context: ApiContext,
    published_app: PublishedApp,
    png_bytes: bytes,
) -> None:
    created = create_bug(context, published_app, png_bytes=png_bytes)
    assert created.status_code == 201
    bug = created.json()
    url = bug["attachments"][0]["url"]

    peer_detail = context.client.get(
        f"/api/v1/bugs/{bug['id']}",
        headers=published_app.bob_auth.bearer,
    )
    assert peer_detail.status_code == 200
    assert peer_detail.json()["attachments"] == []
    assert context.client.get(url, headers=published_app.bob_auth.bearer).status_code == 404

    outsider_auth = context.login(context.outsider)
    assert context.client.get(url, headers=outsider_auth.bearer).status_code == 404
    assert context.client.get(url, headers=published_app.admin_auth.bearer).status_code == 200


def test_admin_soft_deletes_and_restores_bug_without_losing_evidence(
    context: ApiContext,
    published_app: PublishedApp,
    png_bytes: bytes,
) -> None:
    created = create_bug(context, published_app, png_bytes=png_bytes)
    assert created.status_code == 201
    bug = created.json()
    bug_id = bug["id"]
    attachment_url = bug["attachments"][0]["url"]

    deleted = context.client.patch(
        f"/api/v1/admin/bugs/{bug_id}/deletion",
        headers=published_app.admin_auth.bearer,
        json={"deleted": True},
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted_at"] is not None

    current = context.client.get("/api/v1/admin/bugs", headers=published_app.admin_auth.bearer)
    assert current.status_code == 200
    assert current.json()["total"] == 0
    trash = context.client.get(
        "/api/v1/admin/bugs?deleted=true",
        headers=published_app.admin_auth.bearer,
    )
    assert trash.status_code == 200
    assert trash.json()["items"][0]["id"] == bug_id

    assert (
        context.client.get(f"/api/v1/bugs/{bug_id}", headers=published_app.alice_auth.bearer).status_code
        == 404
    )
    assert context.client.get(attachment_url, headers=published_app.admin_auth.bearer).status_code == 404
    cannot_comment = context.client.post(
        f"/api/v1/admin/bugs/{bug_id}/comments",
        headers=published_app.admin_auth.bearer,
        json={"content": "删除后不应继续处理", "internal": True},
    )
    assert cannot_comment.status_code == 409
    assert error_code(cannot_comment) == "bug_deleted"
    dashboard = context.client.get("/api/v1/admin/dashboard", headers=published_app.admin_auth.bearer)
    assert dashboard.status_code == 200
    assert dashboard.json()["open_bugs"] == 0

    restored = context.client.patch(
        f"/api/v1/admin/bugs/{bug_id}/deletion",
        headers=published_app.admin_auth.bearer,
        json={"deleted": False},
    )
    assert restored.status_code == 200
    assert restored.json()["deleted_at"] is None
    assert (
        context.client.get(f"/api/v1/bugs/{bug_id}", headers=published_app.alice_auth.bearer).status_code
        == 200
    )
    assert context.client.get(attachment_url, headers=published_app.admin_auth.bearer).status_code == 200


def test_private_bug_is_invisible_to_peer_and_outside_group(
    context: ApiContext,
    published_app: PublishedApp,
) -> None:
    created = create_bug(context, published_app, visibility="private")
    assert created.status_code == 201
    bug_id = created.json()["id"]

    reporter = context.client.get(
        f"/api/v1/bugs/{bug_id}",
        headers=published_app.alice_auth.bearer,
    )
    assert reporter.status_code == 200
    for auth in (published_app.bob_auth, context.login(context.outsider)):
        detail = context.client.get(f"/api/v1/bugs/{bug_id}", headers=auth.bearer)
        assert detail.status_code == 404
        assert error_code(detail) == "bug_not_found"

    peer_listing = context.client.get("/api/v1/bugs", headers=published_app.bob_auth.bearer)
    assert peer_listing.status_code == 200
    assert peer_listing.json()["total"] == 0
    admin = context.client.get(
        f"/api/v1/admin/bugs/{bug_id}",
        headers=published_app.admin_auth.bearer,
    )
    assert admin.status_code == 200


def test_reporter_can_edit_pending_bug_text_only_before_processing(
    context: ApiContext,
    published_app: PublishedApp,
) -> None:
    created = create_bug(context, published_app)
    assert created.status_code == 201
    bug_id = created.json()["id"]

    empty = context.client.patch(
        f"/api/v1/bugs/{bug_id}",
        headers=published_app.alice_auth.bearer,
        json={},
    )
    assert empty.status_code == 422
    assert error_code(empty) == "validation_error"

    null_title = context.client.patch(
        f"/api/v1/bugs/{bug_id}",
        headers=published_app.alice_auth.bearer,
        json={"title": None},
    )
    assert null_title.status_code == 422

    peer = context.client.patch(
        f"/api/v1/bugs/{bug_id}",
        headers=published_app.bob_auth.bearer,
        json={"title": "不应允许同组用户修改"},
    )
    assert peer.status_code == 404
    assert error_code(peer) == "bug_not_found"

    edited = context.client.patch(
        f"/api/v1/bugs/{bug_id}",
        headers=published_app.alice_auth.bearer,
        json={
            "title": "修正后的列表错位标题",
            "description": "补充：只有切换到深色模式后才会稳定复现。",
            "reproduction_steps": "打开深色模式；进入首页；快速滚动。",
        },
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["title"] == "修正后的列表错位标题"
    assert edited.json()["description"].startswith("补充")
    assert edited.json()["reproduction_steps"].startswith("打开深色模式")

    in_progress = context.client.patch(
        f"/api/v1/admin/bugs/{bug_id}/status",
        headers=published_app.admin_auth.bearer,
        json={"status": "in_progress", "note": "已开始处理"},
    )
    assert in_progress.status_code == 200
    locked = context.client.patch(
        f"/api/v1/bugs/{bug_id}",
        headers=published_app.alice_auth.bearer,
        json={"description": "这个修改发生得太晚"},
    )
    assert locked.status_code == 409
    assert error_code(locked) == "bug_already_processing"

    detail = context.client.get(
        f"/api/v1/bugs/{bug_id}",
        headers=published_app.alice_auth.bearer,
    )
    assert detail.status_code == 200
    assert detail.json()["description"].startswith("补充")


def test_invalid_attachment_rolls_back_database_and_storage(
    context: ApiContext,
    published_app: PublishedApp,
) -> None:
    before_files = {path for path in context.runtime.storage.root.rglob("*") if path.is_file()}
    with context.runtime.database.session() as db:
        before_bugs = int(db.scalar(select(func.count(Bug.id))) or 0)
        before_attachments = int(db.scalar(select(func.count(BugAttachment.id))) or 0)

    response = create_bug(context, published_app, png_bytes=b"not-a-real-png")
    assert response.status_code == 422
    assert error_code(response) == "invalid_attachment"

    after_files = {path for path in context.runtime.storage.root.rglob("*") if path.is_file()}
    assert after_files == before_files
    with context.runtime.database.session() as db:
        assert db.scalar(select(func.count(Bug.id))) == before_bugs
        assert db.scalar(select(func.count(BugAttachment.id))) == before_attachments


def test_attachment_limit_is_enforced_before_writing_files(
    context: ApiContext,
    published_app: PublishedApp,
    png_bytes: bytes,
) -> None:
    before_files = {path for path in context.runtime.storage.root.rglob("*") if path.is_file()}
    files = [("files", (f"shot-{index}.png", png_bytes, "image/png")) for index in range(6)]
    response = context.client.post(
        "/api/v1/bugs",
        headers=published_app.alice_auth.bearer,
        data={
            "app_id": published_app.app_id,
            "version_id": published_app.version_id,
            "title": "附件数量超限",
            "description": "这个请求不应创建任何半成品。",
        },
        files=files,
    )
    assert response.status_code == 422
    assert error_code(response) == "attachment_limit"
    assert {path for path in context.runtime.storage.root.rglob("*") if path.is_file()} == before_files


def test_admin_and_reporter_enforce_bug_state_machine(
    context: ApiContext,
    published_app: PublishedApp,
) -> None:
    created = create_bug(context, published_app)
    assert created.status_code == 201
    bug_id = created.json()["id"]

    invalid = context.client.patch(
        f"/api/v1/admin/bugs/{bug_id}/status",
        headers=published_app.admin_auth.bearer,
        json={"status": "verifying", "fix_version_id": published_app.version_id},
    )
    assert invalid.status_code == 409
    assert error_code(invalid) == "invalid_bug_transition"

    missing_resolution = context.client.patch(
        f"/api/v1/admin/bugs/{bug_id}/status",
        headers=published_app.admin_auth.bearer,
        json={"status": "closed", "note": "缺少结论"},
    )
    assert missing_resolution.status_code == 422
    assert error_code(missing_resolution) == "validation_error"

    in_progress = context.client.patch(
        f"/api/v1/admin/bugs/{bug_id}/status",
        headers=published_app.admin_auth.bearer,
        json={"status": "in_progress", "note": "已分派给 Android 团队"},
    )
    assert in_progress.status_code == 200
    assert in_progress.json()["status"] == "in_progress"

    verifying = context.client.patch(
        f"/api/v1/admin/bugs/{bug_id}/status",
        headers=published_app.admin_auth.bearer,
        json={
            "status": "verifying",
            "note": "请验证修复",
            "fix_version_id": published_app.version_id,
        },
    )
    assert verifying.status_code == 200
    assert verifying.json()["fix_version_id"] == published_app.version_id

    peer_verify = context.client.post(
        f"/api/v1/bugs/{bug_id}/verification",
        headers=published_app.bob_auth.bearer,
        json={"accepted": True, "note": "越权验证"},
    )
    assert peer_verify.status_code == 404

    rejected = context.client.post(
        f"/api/v1/bugs/{bug_id}/verification",
        headers=published_app.alice_auth.bearer,
        json={"accepted": False, "note": "仍能复现"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "in_progress"
    assert rejected.json()["resolution"] is None

    verifying_again = context.client.patch(
        f"/api/v1/admin/bugs/{bug_id}/status",
        headers=published_app.admin_auth.bearer,
        json={
            "status": "verifying",
            "note": "第二次修复",
            "fix_version_id": published_app.version_id,
        },
    )
    assert verifying_again.status_code == 200
    accepted = context.client.post(
        f"/api/v1/bugs/{bug_id}/verification",
        headers=published_app.alice_auth.bearer,
        json={"accepted": True, "note": "验证通过"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "closed"
    assert accepted.json()["resolution"] == "fixed"
    assert accepted.json()["closed_at"] is not None
    assert [item["to_status"] for item in accepted.json()["transitions"]] == [
        "pending",
        "in_progress",
        "verifying",
        "in_progress",
        "verifying",
        "closed",
    ]


def test_internal_admin_note_is_visible_to_admin_only(
    context: ApiContext,
    published_app: PublishedApp,
) -> None:
    created = create_bug(context, published_app)
    assert created.status_code == 201
    bug_id = created.json()["id"]
    public = context.client.post(
        f"/api/v1/admin/bugs/{bug_id}/comments",
        headers=published_app.admin_auth.bearer,
        json={"content": "已收到，将在下一版修复", "internal": False},
    )
    assert public.status_code == 200
    internal = context.client.post(
        f"/api/v1/admin/bugs/{bug_id}/comments",
        headers=published_app.admin_auth.bearer,
        json={"content": "内部排查：与缓存迁移有关", "internal": True},
    )
    assert internal.status_code == 200

    admin_detail = context.client.get(
        f"/api/v1/admin/bugs/{bug_id}",
        headers=published_app.admin_auth.bearer,
    )
    assert admin_detail.status_code == 200
    assert [(item["content"], item["is_admin_note"]) for item in admin_detail.json()["comments"]] == [
        ("已收到，将在下一版修复", False),
        ("内部排查：与缓存迁移有关", True),
    ]

    reporter_detail = context.client.get(
        f"/api/v1/bugs/{bug_id}",
        headers=published_app.alice_auth.bearer,
    )
    assert reporter_detail.status_code == 200
    assert [item["content"] for item in reporter_detail.json()["comments"]] == ["已收到，将在下一版修复"]
    with context.runtime.database.session() as db:
        internal_count = db.scalar(
            select(func.count(BugComment.id)).where(
                BugComment.bug_id == bug_id,
                BugComment.is_admin_note.is_(True),
            )
        )
        assert internal_count == 1


def test_revoking_app_access_also_revokes_peer_bug_access(
    context: ApiContext,
    published_app: PublishedApp,
) -> None:
    created = create_bug(context, published_app)
    assert created.status_code == 201
    bug_id = created.json()["id"]
    assert (
        context.client.get(f"/api/v1/bugs/{bug_id}", headers=published_app.bob_auth.bearer).status_code == 200
    )

    updated = context.client.patch(
        f"/api/v1/admin/groups/{published_app.group_id}",
        headers=published_app.admin_auth.bearer,
        json={"member_ids": [context.alice.id]},
    )
    assert updated.status_code == 200
    revoked = context.client.get(f"/api/v1/bugs/{bug_id}", headers=published_app.bob_auth.bearer)
    assert revoked.status_code == 404
    assert error_code(revoked) == "bug_not_found"


def test_cross_app_version_cannot_be_used_to_submit_bug(
    context: ApiContext,
    published_app: PublishedApp,
) -> None:
    second_app = context.create_app(
        published_app.admin_auth,
        group_ids=[published_app.group_id],
        package_name="com.example.second",
        name="第二个应用",
    )
    response = context.client.post(
        "/api/v1/bugs",
        headers=published_app.alice_auth.bearer,
        data={
            "app_id": second_app["id"],
            "version_id": published_app.version_id,
            "title": "跨应用版本",
            "description": "不允许把其他应用的版本绑定到这个 Bug。",
        },
    )
    assert response.status_code == 404
    assert error_code(response) == "app_version_not_found"

    with context.runtime.database.session() as db:
        count = db.scalar(select(func.count(Bug.id)).where(Bug.app_id == second_app["id"]))
        assert count == 0
