from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.sql import Select

from beta_center.dependencies import (
    Principal,
    get_db,
    get_runtime,
    request_ip,
    require_admin,
    require_admin_csrf,
    require_recent_admin,
)
from beta_center.models import AppVersion, Bug, BugComment, BugStatus, BugTransition, utc_now
from beta_center.presenters import bug_summary
from beta_center.runtime import Runtime
from beta_center.schemas import (
    AdminBugCommentCreate,
    BugDeletionUpdate,
    BugStatusUpdate,
    BugSummary,
    BugVisibilityUpdate,
    Page,
    PermanentDeleteRequest,
)
from beta_center.services.admin_confirmation import confirm_permanent_delete_password
from beta_center.services.audit import record_audit
from beta_center.services.storage import StorageError

router = APIRouter(prefix="/api/v1/admin/bugs", tags=["admin-bugs"])
logger = logging.getLogger("beta_center.admin_bugs")

_TRANSITIONS: dict[BugStatus, set[BugStatus]] = {
    BugStatus.PENDING: {BugStatus.IN_PROGRESS, BugStatus.CLOSED},
    BugStatus.IN_PROGRESS: {BugStatus.VERIFYING, BugStatus.CLOSED},
    BugStatus.VERIFYING: {BugStatus.IN_PROGRESS, BugStatus.CLOSED},
    BugStatus.CLOSED: set(),
}


@router.get("", response_model=Page[BugSummary])
def list_admin_bugs(
    app_id: str | None = None,
    reporter_id: str | None = None,
    bug_status: BugStatus | None = Query(default=None, alias="status"),
    deleted: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db, scope="function"),
) -> Page[BugSummary]:
    query = _bug_query()
    count_query = select(func.count(Bug.id))
    deleted_predicate = Bug.deleted_at.is_not(None) if deleted else Bug.deleted_at.is_(None)
    query = query.where(deleted_predicate)
    count_query = count_query.where(deleted_predicate)
    if app_id:
        query = query.where(Bug.app_id == app_id)
        count_query = count_query.where(Bug.app_id == app_id)
    if reporter_id:
        query = query.where(Bug.reporter_id == reporter_id)
        count_query = count_query.where(Bug.reporter_id == reporter_id)
    if bug_status is not None:
        query = query.where(Bug.status == bug_status)
        count_query = count_query.where(Bug.status == bug_status)
    total = int(db.scalar(count_query) or 0)
    bugs = db.scalars(
        query.order_by(Bug.updated_at.desc(), Bug.id.desc()).offset((page - 1) * page_size).limit(page_size)
    ).unique()
    return Page(
        items=[_admin_bug_summary(bug) for bug in bugs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{bug_id}", response_model=BugSummary)
def get_admin_bug(
    bug_id: str,
    _principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db, scope="function"),
) -> BugSummary:
    return _admin_bug_summary(_get_bug(db, bug_id))


@router.patch("/{bug_id}/status", response_model=BugSummary)
def update_bug_status(
    bug_id: str,
    payload: BugStatusUpdate,
    request: Request,
    principal: Principal = Depends(require_admin_csrf),
    db: Session = Depends(get_db, scope="function"),
) -> BugSummary:
    bug = _get_bug(db, bug_id, lock=True)
    _ensure_active(bug)
    if payload.status == bug.status:
        return _admin_bug_summary(bug)
    if payload.status not in _TRANSITIONS[bug.status]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "invalid_bug_transition", "message": "不允许执行该 Bug 状态变更"},
        )
    fix_version = None
    if payload.fix_version_id:
        fix_version = db.get(AppVersion, payload.fix_version_id)
        if fix_version is None or fix_version.app_id != bug.app_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"code": "invalid_fix_version", "message": "修复版本不属于该应用"},
            )
    old_status = bug.status
    bug.status = payload.status
    bug.fix_version_id = fix_version.id if fix_version else None
    if payload.status == BugStatus.CLOSED:
        bug.resolution = payload.resolution
        bug.resolution_note = payload.note
        bug.closed_at = utc_now()
    else:
        bug.resolution = None
        bug.resolution_note = ""
        bug.closed_at = None
    db.add(
        BugTransition(
            bug_id=bug.id,
            actor_id=principal.user.id,
            from_status=old_status,
            to_status=payload.status,
            note=payload.note,
        )
    )
    record_audit(
        db,
        actor=principal.user,
        action="admin.bug.transition",
        entity_type="bug",
        entity_id=bug.id,
        details={"from": old_status.value, "to": payload.status.value, "resolution": payload.resolution},
        request_ip=request_ip(request),
    )
    db.flush()
    db.expire(bug, ["transitions"])
    return _admin_bug_summary(_get_bug(db, bug.id))


@router.patch("/{bug_id}/visibility", response_model=BugSummary)
def update_bug_visibility(
    bug_id: str,
    payload: BugVisibilityUpdate,
    request: Request,
    principal: Principal = Depends(require_admin_csrf),
    db: Session = Depends(get_db, scope="function"),
) -> BugSummary:
    bug = _get_bug(db, bug_id, lock=True)
    _ensure_active(bug)
    bug.visibility = payload.visibility
    record_audit(
        db,
        actor=principal.user,
        action="admin.bug.visibility",
        entity_type="bug",
        entity_id=bug.id,
        details={"visibility": payload.visibility.value},
        request_ip=request_ip(request),
    )
    db.flush()
    return _admin_bug_summary(_get_bug(db, bug.id))


@router.post("/{bug_id}/comments", response_model=BugSummary)
def add_admin_comment(
    bug_id: str,
    payload: AdminBugCommentCreate,
    request: Request,
    principal: Principal = Depends(require_admin_csrf),
    db: Session = Depends(get_db, scope="function"),
) -> BugSummary:
    bug = _get_bug(db, bug_id)
    _ensure_active(bug)
    comment = BugComment(
        bug_id=bug.id,
        author_id=principal.user.id,
        content=payload.content,
        is_admin_note=payload.internal,
    )
    db.add(comment)
    bug.updated_at = utc_now()
    db.flush()
    record_audit(
        db,
        actor=principal.user,
        action="admin.bug.comment",
        entity_type="bug_comment",
        entity_id=comment.id,
        details={"bug_id": bug.id, "internal": payload.internal},
        request_ip=request_ip(request),
    )
    db.expire(bug, ["comments"])
    return _admin_bug_summary(_get_bug(db, bug.id))


@router.patch("/{bug_id}/deletion", response_model=BugSummary)
def update_bug_deletion(
    bug_id: str,
    payload: BugDeletionUpdate,
    request: Request,
    principal: Principal = Depends(require_recent_admin),
    db: Session = Depends(get_db, scope="function"),
) -> BugSummary:
    bug = _get_bug(db, bug_id, lock=True)
    currently_deleted = bug.deleted_at is not None
    if payload.deleted == currently_deleted:
        return _admin_bug_summary(bug)
    changed_at = utc_now()
    bug.deleted_at = changed_at if payload.deleted else None
    bug.updated_at = changed_at
    record_audit(
        db,
        actor=principal.user,
        action="admin.bug.delete" if payload.deleted else "admin.bug.restore",
        entity_type="bug",
        entity_id=bug.id,
        details={"soft_delete": True},
        request_ip=request_ip(request),
    )
    db.flush()
    return _admin_bug_summary(_get_bug(db, bug.id))


@router.delete("/{bug_id}", status_code=status.HTTP_204_NO_CONTENT)
def permanently_delete_bug(
    bug_id: str,
    payload: PermanentDeleteRequest,
    request: Request,
    principal: Principal = Depends(require_admin_csrf),
    db: Session = Depends(get_db, scope="function"),
    runtime: Runtime = Depends(get_runtime),
) -> Response:
    bug = _get_bug(db, bug_id, lock=True)
    if bug.deleted_at is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "bug_must_be_deleted", "message": "Bug 必须先删除，才能永久删除"},
        )
    ip = request_ip(request)
    confirm_permanent_delete_password(
        db,
        runtime.settings,
        actor=principal.user,
        auth_session=principal.session,
        password=payload.current_password,
        request_ip=ip,
        action="admin.bug.permanent_delete",
        entity_type="bug",
        entity_id=bug.id,
    )
    storage_keys = {attachment.storage_key for attachment in bug.attachments}
    reference = f"BUG-{bug.id[:8].upper()}"
    record_audit(
        db,
        actor=principal.user,
        action="admin.bug.permanent_delete",
        entity_type="bug",
        entity_id=bug.id,
        details={"reference": reference, "attachment_count": len(storage_keys)},
        request_ip=ip,
    )
    db.delete(bug)
    db.commit()
    for storage_key in storage_keys:
        try:
            runtime.storage.delete(storage_key)
        except (OSError, StorageError):
            logger.exception("Could not remove permanently deleted Bug object %s", storage_key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _admin_bug_summary(bug: Bug) -> BugSummary:
    return bug_summary(bug, include_attachments=True, include_internal_notes=True)


def _bug_query() -> Select[tuple[Bug]]:
    return select(Bug).options(
        selectinload(Bug.app),
        selectinload(Bug.version),
        selectinload(Bug.reporter),
        selectinload(Bug.attachments),
        selectinload(Bug.comments).selectinload(BugComment.author),
        selectinload(Bug.transitions).selectinload(BugTransition.actor),
    )


def _get_bug(db: Session, bug_id: str, *, lock: bool = False) -> Bug:
    query = _bug_query().where(Bug.id == bug_id)
    if lock:
        query = query.with_for_update(of=Bug)
    bug = db.scalar(query)
    if bug is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "bug_not_found", "message": "Bug 不存在"},
        )
    return bug


def _ensure_active(bug: Bug) -> None:
    if bug.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "bug_deleted", "message": "已删除的 Bug 只能先恢复，再继续处理"},
        )
