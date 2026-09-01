from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload, with_loader_criteria
from sqlalchemy.sql import Select

from beta_center.dependencies import Principal, get_db, get_runtime, require_csrf, require_ready_user
from beta_center.models import (
    App,
    AppVersion,
    Bug,
    BugAttachment,
    BugComment,
    BugResolution,
    BugStatus,
    BugTransition,
    BugVisibility,
    User,
    utc_now,
)
from beta_center.presenters import bug_summary
from beta_center.runtime import Runtime
from beta_center.schemas import (
    BugCommentCreate,
    BugCreate,
    BugSummary,
    BugTextUpdate,
    BugVerificationRequest,
    Page,
)
from beta_center.services.access import accessible_app_ids_query, user_can_access_app, user_can_view_bug
from beta_center.services.storage import StorageError

router = APIRouter(prefix="/api/v1/bugs", tags=["bugs"])


@router.get("", response_model=Page[BugSummary], response_model_exclude_none=True)
def list_bugs(
    mine: bool = False,
    app_id: str | None = None,
    bug_status: BugStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    principal: Principal = Depends(require_ready_user),
    db: Session = Depends(get_db, scope="function"),
) -> Page[BugSummary]:
    accessible_ids = accessible_app_ids_query(principal.user)
    visibility = or_(
        Bug.reporter_id == principal.user.id,
        and_(Bug.visibility == BugVisibility.GROUP, Bug.app_id.in_(accessible_ids)),
    )
    query = _bug_query().where(visibility, Bug.deleted_at.is_(None))
    count_query = select(func.count(Bug.id)).where(visibility, Bug.deleted_at.is_(None))
    if mine:
        query = query.where(Bug.reporter_id == principal.user.id)
        count_query = count_query.where(Bug.reporter_id == principal.user.id)
    if app_id:
        query = query.where(Bug.app_id == app_id)
        count_query = count_query.where(Bug.app_id == app_id)
    if bug_status is not None:
        query = query.where(Bug.status == bug_status)
        count_query = count_query.where(Bug.status == bug_status)
    # The list endpoint is exercised frequently by the client. A window count
    # avoids a second visibility/count round trip for normal non-empty pages.
    # Keep the separate count as an empty-page fallback so pagination semantics
    # remain unchanged when the requested offset is past the final row.
    rows = db.execute(
        query.add_columns(func.count(Bug.id).over().label("page_total"))
        .order_by(Bug.updated_at.desc(), Bug.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).unique()
    page_rows = rows.all()
    total = int(page_rows[0].page_total) if page_rows else int(db.scalar(count_query) or 0)
    bugs = [row.Bug for row in page_rows]
    return Page(
        items=[
            bug_summary(
                bug,
                include_attachments=bug.reporter_id == principal.user.id,
                include_reporter_identity=bug.reporter_id == principal.user.id,
                include_sensitive_details=bug.reporter_id == principal.user.id,
            )
            for bug in bugs
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=BugSummary, status_code=status.HTTP_201_CREATED)
async def create_bug(
    app_id: str = Form(...),
    version_id: str = Form(...),
    title: str = Form(..., min_length=2, max_length=120),
    description: str = Form(..., min_length=2, max_length=10_000),
    reproduction_steps: str = Form(default="", max_length=5000),
    device_model: str = Form(default="", max_length=120),
    android_version: str = Form(default="", max_length=50),
    client_version: str = Form(default="", max_length=50),
    visibility: BugVisibility = Form(default=BugVisibility.GROUP),
    files: list[UploadFile] = File(default=[]),
    principal: Principal = Depends(require_csrf),
    db: Session = Depends(get_db, scope="function"),
    runtime: Runtime = Depends(get_runtime),
) -> BugSummary:
    if principal.user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "password_change_required", "message": "首次登录必须先修改初始密码"},
        )
    payload = BugCreate(
        app_id=app_id,
        version_id=version_id,
        title=title,
        description=description,
        reproduction_steps=reproduction_steps,
        device_model=device_model,
        android_version=android_version,
        client_version=client_version,
        visibility=visibility,
    )
    if len(files) > runtime.settings.max_bug_attachments:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "attachment_limit",
                "message": f"Bug 截图最多上传 {runtime.settings.max_bug_attachments} 张",
            },
        )
    version = db.get(AppVersion, payload.version_id)
    if (
        version is None
        or version.app_id != payload.app_id
        or not user_can_access_app(db, principal.user, payload.app_id)
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "app_version_not_found", "message": "应用版本不存在或你没有访问权限"},
        )
    stored_files = []
    try:
        for file in files:
            stored_files.append(
                await runtime.storage.save_image(
                    file,
                    namespace="bug-attachments",
                    max_bytes=runtime.settings.max_image_bytes,
                )
            )
    except StorageError as exc:
        for stored in stored_files:
            runtime.storage.delete(stored.key)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "invalid_attachment", "message": str(exc)},
        ) from exc
    bug = Bug(
        app_id=payload.app_id,
        version_id=payload.version_id,
        reporter_id=principal.user.id,
        title=payload.title,
        description=payload.description,
        reproduction_steps=payload.reproduction_steps,
        device_model=payload.device_model,
        android_version=payload.android_version,
        client_version=payload.client_version,
        visibility=payload.visibility,
    )
    try:
        db.add(bug)
        db.flush()
        for stored in stored_files:
            db.add(
                BugAttachment(
                    bug_id=bug.id,
                    storage_key=stored.key,
                    content_type=stored.content_type,
                    file_size=stored.size,
                    sha256=stored.sha256,
                )
            )
        db.add(
            BugTransition(
                bug_id=bug.id,
                actor_id=principal.user.id,
                from_status=None,
                to_status=BugStatus.PENDING,
                note="用户提交 Bug",
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        for stored in stored_files:
            runtime.storage.delete(stored.key)
        raise
    return bug_summary(_get_bug(db, bug.id), include_attachments=True)


@router.get("/{bug_id}", response_model=BugSummary, response_model_exclude_none=True)
def get_bug(
    bug_id: str,
    principal: Principal = Depends(require_ready_user),
    db: Session = Depends(get_db, scope="function"),
) -> BugSummary:
    bug = _get_bug(db, bug_id)
    if not user_can_view_bug(db, principal.user, bug):
        raise _bug_not_found()
    is_reporter = bug.reporter_id == principal.user.id
    return bug_summary(
        bug,
        include_attachments=is_reporter,
        include_reporter_identity=is_reporter,
        include_sensitive_details=is_reporter,
    )


@router.patch("/{bug_id}", response_model=BugSummary, response_model_exclude_none=True)
def update_bug_text(
    bug_id: str,
    payload: BugTextUpdate,
    principal: Principal = Depends(require_csrf),
    db: Session = Depends(get_db, scope="function"),
) -> BugSummary:
    bug = _get_bug(db, bug_id, lock=True)
    if bug.reporter_id != principal.user.id:
        raise _bug_not_found()
    if bug.status != BugStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "bug_already_processing", "message": "管理员开始处理后不能再修改问题文本"},
        )
    changes = payload.model_dump(exclude_unset=True)
    if "title" in changes:
        bug.title = changes["title"]
    if "description" in changes:
        bug.description = changes["description"]
    if "reproduction_steps" in changes:
        bug.reproduction_steps = changes["reproduction_steps"]
    bug.updated_at = utc_now()
    db.flush()
    return bug_summary(_get_bug(db, bug.id), include_attachments=True)


@router.post("/{bug_id}/comments", response_model=BugSummary, response_model_exclude_none=True)
def add_comment(
    bug_id: str,
    payload: BugCommentCreate,
    principal: Principal = Depends(require_csrf),
    db: Session = Depends(get_db, scope="function"),
) -> BugSummary:
    bug = _get_bug(db, bug_id)
    if not user_can_view_bug(db, principal.user, bug):
        raise _bug_not_found()
    db.add(BugComment(bug_id=bug.id, author_id=principal.user.id, content=payload.content))
    bug.updated_at = utc_now()
    db.flush()
    db.expire(bug, ["comments"])
    is_reporter = bug.reporter_id == principal.user.id
    return bug_summary(
        _get_bug(db, bug.id),
        include_attachments=is_reporter,
        include_reporter_identity=is_reporter,
        include_sensitive_details=is_reporter,
    )


@router.post("/{bug_id}/verification", response_model=BugSummary)
def verify_bug(
    bug_id: str,
    payload: BugVerificationRequest,
    principal: Principal = Depends(require_csrf),
    db: Session = Depends(get_db, scope="function"),
) -> BugSummary:
    bug = _get_bug(db, bug_id, lock=True)
    if bug.reporter_id != principal.user.id:
        raise _bug_not_found()
    if bug.status != BugStatus.VERIFYING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "bug_not_verifying", "message": "该 Bug 当前不处于待验证状态"},
        )
    old_status = bug.status
    if payload.accepted:
        bug.status = BugStatus.CLOSED
        bug.resolution = BugResolution.FIXED
        bug.resolution_note = payload.note or "测试用户验证通过"
        bug.closed_at = utc_now()
    else:
        bug.status = BugStatus.IN_PROGRESS
        bug.resolution = None
        bug.resolution_note = ""
        bug.fix_version_id = None
        bug.closed_at = None
    db.add(
        BugTransition(
            bug_id=bug.id,
            actor_id=principal.user.id,
            from_status=old_status,
            to_status=bug.status,
            note=payload.note or ("验证通过" if payload.accepted else "问题仍然存在"),
        )
    )
    db.flush()
    db.expire(bug, ["transitions"])
    return bug_summary(_get_bug(db, bug.id), include_attachments=True)


def _bug_query() -> Select[tuple[Bug]]:
    return select(Bug).options(
        # These are scalar relationships. Joining them cannot multiply Bug
        # rows and removes three fixed select-in round trips per non-empty page.
        joinedload(Bug.app).load_only(App.id, App.name).raiseload(App.visible_groups),
        joinedload(Bug.version).load_only(AppVersion.id, AppVersion.version_name),
        joinedload(Bug.reporter).load_only(User.id, User.display_name).raiseload(User.groups),
        selectinload(Bug.attachments).load_only(
            BugAttachment.id,
            BugAttachment.bug_id,
            BugAttachment.content_type,
            BugAttachment.file_size,
            BugAttachment.created_at,
        ),
        # Keep collections select-in loaded to avoid a comments x transitions
        # cartesian product, but join each collection's scalar user relation.
        selectinload(Bug.comments)
        .load_only(
            BugComment.id,
            BugComment.bug_id,
            BugComment.author_id,
            BugComment.content,
            BugComment.is_admin_note,
            BugComment.created_at,
        )
        .joinedload(BugComment.author)
        .load_only(User.id, User.display_name)
        .raiseload(User.groups),
        selectinload(Bug.transitions)
        .load_only(
            BugTransition.id,
            BugTransition.bug_id,
            BugTransition.actor_id,
            BugTransition.from_status,
            BugTransition.to_status,
            BugTransition.note,
            BugTransition.created_at,
        )
        .joinedload(BugTransition.actor)
        .load_only(User.id, User.display_name)
        .raiseload(User.groups),
        # User responses never expose internal administrator notes. Filter them
        # in SQL instead of loading their potentially large text into memory.
        with_loader_criteria(BugComment, BugComment.is_admin_note.is_(False), include_aliases=True),
    )


def _get_bug(db: Session, bug_id: str, *, lock: bool = False) -> Bug:
    query = _bug_query().where(Bug.id == bug_id, Bug.deleted_at.is_(None))
    if lock:
        # The eager scalar relationships above are LEFT OUTER JOINs. PostgreSQL
        # cannot lock their nullable sides, so lock only the Bug row that this
        # mutation protects.
        query = query.with_for_update(of=Bug)
    bug = db.scalar(query)
    if bug is None:
        raise _bug_not_found()
    return bug


def _bug_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "bug_not_found", "message": "Bug 不存在或你没有访问权限"},
    )
