from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from beta_center.dependencies import Principal, get_db, require_ready_user
from beta_center.models import App, AppStatus
from beta_center.presenters import app_detail, app_summary
from beta_center.schemas import AppDetail, AppSummary
from beta_center.services.access import accessible_app_ids_query, user_can_access_app

router = APIRouter(prefix="/api/v1/apps", tags=["apps"])


@router.get("", response_model=list[AppSummary])
def list_assigned_apps(
    search: str = Query(default="", max_length=100),
    principal: Principal = Depends(require_ready_user),
    db: Session = Depends(get_db, scope="function"),
) -> list[AppSummary]:
    allowed_ids = accessible_app_ids_query(principal.user)
    query = (
        select(App)
        .where(
            App.id.in_(allowed_ids),
            App.status == AppStatus.PUBLISHED,
            App.current_version_id.is_not(None),
        )
        .options(selectinload(App.visible_groups), selectinload(App.versions))
    )
    if search:
        pattern = f"%{search.strip()}%"
        query = query.where(or_(App.name.ilike(pattern), App.short_description.ilike(pattern)))
    apps = db.scalars(query.order_by(App.updated_at.desc(), App.id.desc())).unique()
    return [app_summary(db, app) for app in apps]


@router.get("/{app_id}", response_model=AppDetail)
def get_assigned_app(
    app_id: str,
    principal: Principal = Depends(require_ready_user),
    db: Session = Depends(get_db, scope="function"),
) -> AppDetail:
    if not user_can_access_app(db, principal.user, app_id):
        raise _not_found()
    app = db.scalar(
        select(App)
        .where(App.id == app_id, App.status == AppStatus.PUBLISHED)
        .options(
            selectinload(App.visible_groups),
            selectinload(App.versions),
            selectinload(App.screenshots),
        )
    )
    if app is None:
        raise _not_found()
    # Testers only need the currently published release. Draft and disabled
    # release metadata belongs to the administrator workflow.
    return app_detail(db, app, include_history=False)


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "app_not_found", "message": "应用不存在或你没有访问权限"},
    )
