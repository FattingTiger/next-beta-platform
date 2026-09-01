from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import delete as sql_delete
from sqlalchemy import func, or_, select, text, update
from sqlalchemy.orm import Session, selectinload

from beta_center.dependencies import (
    Principal,
    get_db,
    get_runtime,
    request_ip,
    require_admin,
    require_admin_csrf,
    require_recent_admin,
)
from beta_center.models import (
    AppVersion,
    AuthSession,
    Bug,
    BugComment,
    BugTransition,
    DownloadRecord,
    TestGroup,
    User,
    UserRole,
    utc_now,
)
from beta_center.presenters import user_summary
from beta_center.runtime import Runtime
from beta_center.schemas import (
    Page,
    PasswordReset,
    PermanentDeleteRequest,
    UserCreate,
    UserSummary,
    UserUpdate,
)
from beta_center.security import hash_password
from beta_center.services.admin_confirmation import confirm_permanent_delete_password
from beta_center.services.audit import record_audit
from beta_center.services.storage import StorageError

router = APIRouter(prefix="/api/v1/admin/users", tags=["admin-users"])
logger = logging.getLogger("beta_center.admin_users")


@router.get("", response_model=Page[UserSummary])
def list_users(
    search: str = Query(default="", max_length=100),
    active: bool | None = None,
    role: UserRole | None = None,
    group_id: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db, scope="function"),
) -> Page[UserSummary]:
    query = select(User).options(selectinload(User.groups))
    count_query = select(func.count(func.distinct(User.id))).select_from(User)
    if search:
        pattern = f"%{search.strip()}%"
        predicate = or_(User.display_name.ilike(pattern), User.phone.ilike(pattern))
        query = query.where(predicate)
        count_query = count_query.where(predicate)
    if active is not None:
        query = query.where(User.is_active.is_(active))
        count_query = count_query.where(User.is_active.is_(active))
    if role is not None:
        query = query.where(User.role == role)
        count_query = count_query.where(User.role == role)
    if group_id:
        query = query.join(User.groups).where(TestGroup.id == group_id)
        count_query = count_query.join(User.groups).where(TestGroup.id == group_id)
    total = int(db.scalar(count_query) or 0)
    users = db.scalars(
        query.order_by(User.created_at.desc(), User.id.desc()).offset((page - 1) * page_size).limit(page_size)
    ).unique()
    return Page(items=[user_summary(user) for user in users], total=total, page=page, page_size=page_size)


@router.post("", response_model=UserSummary, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    request: Request,
    principal: Principal = Depends(require_recent_admin),
    db: Session = Depends(get_db, scope="function"),
) -> UserSummary:
    if payload.role == UserRole.ADMIN:
        _lock_admin_guard(db)
    if db.scalar(select(User.id).where(User.phone == payload.phone)):
        raise _conflict("phone_exists", "该手机号已被使用")
    groups = _load_groups(db, payload.group_ids)
    user = User(
        display_name=payload.display_name,
        phone=payload.phone,
        password_hash=hash_password(payload.initial_password),
        role=payload.role,
        groups=groups,
    )
    db.add(user)
    db.flush()
    record_audit(
        db,
        actor=principal.user,
        action="admin.user.create",
        entity_type="user",
        entity_id=user.id,
        details={"role": user.role.value, "group_ids": payload.group_ids},
        request_ip=request_ip(request),
    )
    return user_summary(user)


@router.get("/{user_id}", response_model=UserSummary)
def get_user(
    user_id: str,
    _principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db, scope="function"),
) -> UserSummary:
    return user_summary(_get_user(db, user_id))


@router.patch("/{user_id}", response_model=UserSummary)
def update_user(
    user_id: str,
    payload: UserUpdate,
    request: Request,
    principal: Principal = Depends(require_recent_admin),
    db: Session = Depends(get_db, scope="function"),
) -> UserSummary:
    if payload.role is not None or payload.is_active is not None:
        _lock_admin_guard(db)
    user = _get_user(db, user_id)
    changes = payload.model_dump(exclude_unset=True)
    if payload.phone and payload.phone != user.phone:
        if db.scalar(select(User.id).where(User.phone == payload.phone, User.id != user.id)):
            raise _conflict("phone_exists", "该手机号已被使用")
        user.phone = payload.phone
    if payload.display_name is not None:
        user.display_name = payload.display_name
    if payload.group_ids is not None:
        user.groups = _load_groups(db, payload.group_ids)
    if payload.role is not None and payload.role != user.role:
        if user.id == principal.user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "cannot_change_own_role", "message": "不能修改自己的管理员角色"},
            )
        if user.role == UserRole.ADMIN and payload.role != UserRole.ADMIN:
            _ensure_another_active_admin(db, user.id)
        user.role = payload.role
        user.session_generation += 1
        _revoke_sessions(db, user.id)
    if payload.is_active is not None and payload.is_active != user.is_active:
        if user.id == principal.user.id and not payload.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "cannot_disable_self", "message": "不能禁用当前管理员账号"},
            )
        if user.role == UserRole.ADMIN and not payload.is_active:
            _ensure_another_active_admin(db, user.id)
        user.is_active = payload.is_active
        user.session_generation += 1
        _revoke_sessions(db, user.id)
    db.flush()
    record_audit(
        db,
        actor=principal.user,
        action="admin.user.update",
        entity_type="user",
        entity_id=user.id,
        details=changes,
        request_ip=request_ip(request),
    )
    return user_summary(user)


@router.post("/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(
    user_id: str,
    payload: PasswordReset,
    request: Request,
    principal: Principal = Depends(require_recent_admin),
    db: Session = Depends(get_db, scope="function"),
) -> None:
    user = _get_user(db, user_id)
    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = payload.force_change
    user.session_generation += 1
    _revoke_sessions(db, user.id)
    record_audit(
        db,
        actor=principal.user,
        action="admin.user.reset_password",
        entity_type="user",
        entity_id=user.id,
        request_ip=request_ip(request),
    )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def permanently_delete_user(
    user_id: str,
    payload: PermanentDeleteRequest,
    request: Request,
    principal: Principal = Depends(require_admin_csrf),
    db: Session = Depends(get_db, scope="function"),
    runtime: Runtime = Depends(get_runtime),
) -> Response:
    if user_id == principal.user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "cannot_delete_self", "message": "不能永久删除当前登录的管理员账号"},
        )
    user = _get_user(db, user_id)
    if user.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "user_must_be_inactive", "message": "用户必须先删除，才能永久删除"},
        )
    created_version_count = int(
        db.scalar(select(func.count(AppVersion.id)).where(AppVersion.created_by_id == user.id)) or 0
    )
    if created_version_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "user_has_published_versions",
                "message": "该账号仍关联已上传的 APK 版本，不能永久删除；可继续保持已删除状态",
            },
        )
    ip = request_ip(request)
    confirm_permanent_delete_password(
        db,
        runtime.settings,
        actor=principal.user,
        auth_session=principal.session,
        password=payload.current_password,
        request_ip=ip,
        action="admin.user.permanent_delete",
        entity_type="user",
        entity_id=user.id,
    )

    reported_bugs = list(
        db.scalars(
            select(Bug).where(Bug.reporter_id == user.id).options(selectinload(Bug.attachments))
        ).unique()
    )
    storage_keys = {attachment.storage_key for bug in reported_bugs for attachment in bug.attachments}
    download_count = int(
        db.scalar(select(func.count(DownloadRecord.id)).where(DownloadRecord.user_id == user.id)) or 0
    )
    db.execute(sql_delete(BugComment).where(BugComment.author_id == user.id))
    db.execute(sql_delete(BugTransition).where(BugTransition.actor_id == user.id))
    db.execute(sql_delete(DownloadRecord).where(DownloadRecord.user_id == user.id))
    for bug in reported_bugs:
        db.delete(bug)
    db.flush()
    record_audit(
        db,
        actor=principal.user,
        action="admin.user.permanent_delete",
        entity_type="user",
        entity_id=user.id,
        details={
            "display_name": user.display_name,
            "phone_suffix": user.phone[-4:],
            "bug_count": len(reported_bugs),
            "download_count": download_count,
        },
        request_ip=ip,
    )
    db.delete(user)
    db.commit()
    for storage_key in storage_keys:
        try:
            runtime.storage.delete(storage_key)
        except (OSError, StorageError):
            logger.exception("Could not remove permanently deleted user object %s", storage_key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _get_user(db: Session, user_id: str) -> User:
    user = db.scalar(select(User).where(User.id == user_id).options(selectinload(User.groups)))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "user_not_found", "message": "用户不存在"},
        )
    return user


def _load_groups(db: Session, group_ids: list[str]) -> list[TestGroup]:
    if not group_ids:
        return []
    groups = list(db.scalars(select(TestGroup).where(TestGroup.id.in_(group_ids))))
    if len(groups) != len(set(group_ids)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_group_ids", "message": "包含不存在的测试组"},
        )
    return groups


def _revoke_sessions(db: Session, user_id: str) -> None:
    db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=utc_now())
    )


def _ensure_another_active_admin(db: Session, excluded_user_id: str) -> None:
    list(db.scalars(select(User.id).where(User.role == UserRole.ADMIN).with_for_update()))
    count = db.scalar(
        select(func.count(User.id)).where(
            User.role == UserRole.ADMIN,
            User.is_active.is_(True),
            User.id != excluded_user_id,
        )
    )
    if not count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "last_admin", "message": "系统必须保留至少一个启用的管理员"},
        )


def _lock_admin_guard(db: Session) -> None:
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        # Stable application-specific key. The transaction-scoped advisory
        # lock serializes all administrator role/activation changes.
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": 4_447_709_445_441})


def _conflict(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": code, "message": message})
