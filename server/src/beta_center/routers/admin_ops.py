from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from beta_center.dependencies import Principal, get_db, require_admin
from beta_center.models import (
    App,
    AppStatus,
    AppVersion,
    AuditLog,
    Bug,
    BugStatus,
    DownloadRecord,
    DownloadStatus,
    User,
    VersionStatus,
)
from beta_center.presenters import audit_summary, download_summary
from beta_center.schemas import AuditSummary, DashboardSummary, DownloadSummary, Page

router = APIRouter(prefix="/api/v1/admin", tags=["admin-operations"])


@router.get("/dashboard", response_model=DashboardSummary)
def dashboard(
    _principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db, scope="function"),
) -> DashboardSummary:
    since = datetime.now(UTC) - timedelta(days=7)
    return DashboardSummary(
        active_users=int(db.scalar(select(func.count(User.id)).where(User.is_active.is_(True))) or 0),
        active_apps=int(db.scalar(select(func.count(App.id)).where(App.status == AppStatus.PUBLISHED)) or 0),
        published_versions=int(
            db.scalar(select(func.count(AppVersion.id)).where(AppVersion.status == VersionStatus.PUBLISHED))
            or 0
        ),
        open_bugs=int(
            db.scalar(
                select(func.count(Bug.id)).where(
                    Bug.status != BugStatus.CLOSED,
                    Bug.deleted_at.is_(None),
                )
            )
            or 0
        ),
        downloads_started_7d=int(
            db.scalar(select(func.count(DownloadRecord.id)).where(DownloadRecord.created_at >= since)) or 0
        ),
        downloads_completed_7d=int(
            db.scalar(
                select(func.count(DownloadRecord.id)).where(
                    DownloadRecord.created_at >= since,
                    DownloadRecord.status == DownloadStatus.COMPLETED,
                )
            )
            or 0
        ),
    )


@router.get("/downloads", response_model=Page[DownloadSummary])
def list_downloads(
    user_id: str | None = None,
    app_id: str | None = None,
    version_id: str | None = None,
    download_status: DownloadStatus | None = Query(default=None, alias="status"),
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db, scope="function"),
) -> Page[DownloadSummary]:
    normalized_from = _download_filter_time(created_from, parameter="created_from")
    normalized_to = _download_filter_time(created_to, parameter="created_to")
    if normalized_from is not None and normalized_to is not None and normalized_from > normalized_to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "invalid_time_range", "message": "开始时间不能晚于结束时间"},
        )
    query = select(DownloadRecord)
    count_query = select(func.count(DownloadRecord.id))
    filters = []
    if user_id:
        filters.append(DownloadRecord.user_id == user_id)
    if app_id:
        filters.append(DownloadRecord.app_id == app_id)
    if version_id:
        filters.append(DownloadRecord.version_id == version_id)
    if download_status is not None:
        filters.append(DownloadRecord.status == download_status)
    if normalized_from is not None:
        filters.append(DownloadRecord.created_at >= normalized_from)
    if normalized_to is not None:
        filters.append(DownloadRecord.created_at <= normalized_to)
    if filters:
        query = query.where(*filters)
        count_query = count_query.where(*filters)
    total = int(db.scalar(count_query) or 0)
    records = db.scalars(
        query.order_by(DownloadRecord.created_at.desc(), DownloadRecord.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return Page(
        items=[download_summary(record) for record in records],
        total=total,
        page=page,
        page_size=page_size,
    )


def _download_filter_time(value: datetime | None, *, parameter: str) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "timezone_required",
                "message": f"{parameter} 必须包含时区偏移",
            },
        )
    return value.astimezone(UTC)


@router.get("/audit-logs", response_model=Page[AuditSummary])
def list_audit_logs(
    action: str = Query(default="", max_length=100),
    actor_id: str | None = None,
    outcome: str = Query(default="", max_length=20),
    reason_code: str = Query(default="", max_length=80),
    request_id: str = Query(default="", max_length=80),
    entity_type: str = Query(default="", max_length=60),
    entity_id: str = Query(default="", max_length=80),
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db, scope="function"),
) -> Page[AuditSummary]:
    query = select(AuditLog).options(selectinload(AuditLog.actor))
    count_query = select(func.count(AuditLog.id))
    if action:
        query = query.where(AuditLog.action == action)
        count_query = count_query.where(AuditLog.action == action)
    if actor_id:
        query = query.where(AuditLog.actor_id == actor_id)
        count_query = count_query.where(AuditLog.actor_id == actor_id)
    for value, column in (
        (outcome, AuditLog.outcome),
        (reason_code, AuditLog.reason_code),
        (request_id, AuditLog.request_id),
        (entity_type, AuditLog.entity_type),
        (entity_id, AuditLog.entity_id),
    ):
        if value:
            query = query.where(column == value)
            count_query = count_query.where(column == value)
    if created_from:
        query = query.where(AuditLog.created_at >= created_from)
        count_query = count_query.where(AuditLog.created_at >= created_from)
    if created_to:
        query = query.where(AuditLog.created_at <= created_to)
        count_query = count_query.where(AuditLog.created_at <= created_to)
    total = int(db.scalar(count_query) or 0)
    entries = db.scalars(
        query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).unique()
    return Page(
        items=[audit_summary(entry) for entry in entries],
        total=total,
        page=page,
        page_size=page_size,
    )
