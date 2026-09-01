from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select
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
from beta_center.models import App, TestGroup, User
from beta_center.presenters import group_summary
from beta_center.runtime import Runtime
from beta_center.schemas import GroupCreate, GroupSummary, GroupUpdate, Page, PermanentDeleteRequest
from beta_center.services.admin_confirmation import confirm_permanent_delete_password
from beta_center.services.audit import record_audit

router = APIRouter(prefix="/api/v1/admin/groups", tags=["admin-groups"])


@router.get("", response_model=Page[GroupSummary])
def list_groups(
    search: str = Query(default="", max_length=100),
    active: bool | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db, scope="function"),
) -> Page[GroupSummary]:
    query = select(TestGroup).options(selectinload(TestGroup.members), selectinload(TestGroup.apps))
    count_query = select(func.count(TestGroup.id))
    if search:
        predicate = TestGroup.name.ilike(f"%{search.strip()}%")
        query = query.where(predicate)
        count_query = count_query.where(predicate)
    if active is not None:
        query = query.where(TestGroup.is_active.is_(active))
        count_query = count_query.where(TestGroup.is_active.is_(active))
    total = int(db.scalar(count_query) or 0)
    groups = db.scalars(
        query.order_by(TestGroup.created_at.desc(), TestGroup.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).unique()
    return Page(items=[group_summary(group) for group in groups], total=total, page=page, page_size=page_size)


@router.post("", response_model=GroupSummary, status_code=status.HTTP_201_CREATED)
def create_group(
    payload: GroupCreate,
    request: Request,
    principal: Principal = Depends(require_recent_admin),
    db: Session = Depends(get_db, scope="function"),
) -> GroupSummary:
    if db.scalar(select(TestGroup.id).where(TestGroup.name == payload.name)):
        raise _conflict("group_name_exists", "测试组名称已存在")
    group = TestGroup(
        name=payload.name,
        description=payload.description,
        members=_load_entities(db, User, payload.member_ids, "用户"),
        apps=_load_entities(db, App, payload.app_ids, "应用"),
    )
    db.add(group)
    db.flush()
    record_audit(
        db,
        actor=principal.user,
        action="admin.group.create",
        entity_type="group",
        entity_id=group.id,
        details={"member_ids": payload.member_ids, "app_ids": payload.app_ids},
        request_ip=request_ip(request),
    )
    return group_summary(group)


@router.get("/{group_id}", response_model=GroupSummary)
def get_group(
    group_id: str,
    _principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db, scope="function"),
) -> GroupSummary:
    return group_summary(_get_group(db, group_id))


@router.patch("/{group_id}", response_model=GroupSummary)
def update_group(
    group_id: str,
    payload: GroupUpdate,
    request: Request,
    principal: Principal = Depends(require_recent_admin),
    db: Session = Depends(get_db, scope="function"),
) -> GroupSummary:
    group = _get_group(db, group_id)
    changes = payload.model_dump(exclude_unset=True)
    if payload.name is not None and payload.name != group.name:
        if db.scalar(select(TestGroup.id).where(TestGroup.name == payload.name, TestGroup.id != group.id)):
            raise _conflict("group_name_exists", "测试组名称已存在")
        group.name = payload.name
    if payload.description is not None:
        group.description = payload.description
    if payload.is_active is not None:
        group.is_active = payload.is_active
    if payload.member_ids is not None:
        group.members = _load_entities(db, User, payload.member_ids, "用户")
    if payload.app_ids is not None:
        group.apps = _load_entities(db, App, payload.app_ids, "应用")
    db.flush()
    record_audit(
        db,
        actor=principal.user,
        action="admin.group.update",
        entity_type="group",
        entity_id=group.id,
        details=changes,
        request_ip=request_ip(request),
    )
    return group_summary(group)


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def permanently_delete_group(
    group_id: str,
    payload: PermanentDeleteRequest,
    request: Request,
    principal: Principal = Depends(require_admin_csrf),
    db: Session = Depends(get_db, scope="function"),
    runtime: Runtime = Depends(get_runtime),
) -> Response:
    group = _get_group(db, group_id)
    if group.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "group_must_be_inactive", "message": "测试组必须先删除，才能永久删除"},
        )
    ip = request_ip(request)
    confirm_permanent_delete_password(
        db,
        runtime.settings,
        actor=principal.user,
        auth_session=principal.session,
        password=payload.current_password,
        request_ip=ip,
        action="admin.group.permanent_delete",
        entity_type="test_group",
        entity_id=group.id,
    )
    record_audit(
        db,
        actor=principal.user,
        action="admin.group.permanent_delete",
        entity_type="test_group",
        entity_id=group.id,
        details={
            "name": group.name,
            "member_count": len(group.members),
            "app_count": len(group.apps),
        },
        request_ip=ip,
    )
    db.delete(group)
    db.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _get_group(db: Session, group_id: str) -> TestGroup:
    group = db.scalar(
        select(TestGroup)
        .where(TestGroup.id == group_id)
        .options(selectinload(TestGroup.members), selectinload(TestGroup.apps))
    )
    if group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "group_not_found", "message": "测试组不存在"},
        )
    return group


def _load_entities[T](db: Session, model: type[T], ids: list[str], label: str) -> list[T]:
    if not ids:
        return []
    entities = list(db.scalars(select(model).where(model.id.in_(ids))))  # type: ignore[attr-defined]
    if len(entities) != len(set(ids)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_assignment_ids", "message": f"包含不存在的{label}"},
        )
    return entities


def _conflict(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": code, "message": message})
