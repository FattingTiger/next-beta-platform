from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from beta_center.dependencies import Principal, get_db, get_runtime, require_ready_user
from beta_center.models import App, AppScreenshot, Bug, BugAttachment
from beta_center.runtime import Runtime
from beta_center.services.access import user_can_access_app, user_can_view_bug_attachment

router = APIRouter(prefix="/api/v1/files", tags=["files"])


@router.get("/apps/{app_id}/icon", response_class=FileResponse)
def app_icon(
    app_id: str,
    principal: Principal = Depends(require_ready_user),
    db: Session = Depends(get_db, scope="function"),
    runtime: Runtime = Depends(get_runtime),
) -> FileResponse:
    app = db.get(App, app_id)
    if app is None or not app.icon_storage_key or not user_can_access_app(db, principal.user, app.id):
        raise _file_not_found()
    return _private_file(runtime, app.icon_storage_key, "image/webp")


@router.get("/apps/{app_id}/screenshots/{screenshot_id}", response_class=FileResponse)
def app_screenshot(
    app_id: str,
    screenshot_id: str,
    principal: Principal = Depends(require_ready_user),
    db: Session = Depends(get_db, scope="function"),
    runtime: Runtime = Depends(get_runtime),
) -> FileResponse:
    item = db.scalar(
        select(AppScreenshot).where(AppScreenshot.id == screenshot_id, AppScreenshot.app_id == app_id)
    )
    if item is None or not user_can_access_app(db, principal.user, app_id):
        raise _file_not_found()
    return _private_file(runtime, item.storage_key, item.content_type)


@router.get("/bugs/{bug_id}/attachments/{attachment_id}", response_class=FileResponse)
def bug_attachment(
    bug_id: str,
    attachment_id: str,
    principal: Principal = Depends(require_ready_user),
    db: Session = Depends(get_db, scope="function"),
    runtime: Runtime = Depends(get_runtime),
) -> FileResponse:
    bug = db.get(Bug, bug_id)
    item = db.scalar(
        select(BugAttachment).where(BugAttachment.id == attachment_id, BugAttachment.bug_id == bug_id)
    )
    if (
        bug is None
        or bug.deleted_at is not None
        or item is None
        or not user_can_view_bug_attachment(db, principal.user, bug)
    ):
        raise _file_not_found()
    return _private_file(runtime, item.storage_key, item.content_type, no_store=True)


def _private_file(
    runtime: Runtime,
    storage_key: str,
    content_type: str,
    *,
    no_store: bool = False,
) -> FileResponse:
    path = runtime.storage.path_for(storage_key)
    if not path.is_file():
        raise _file_not_found()
    return FileResponse(
        path,
        media_type=content_type,
        headers={
            "Cache-Control": "private, no-store" if no_store else "private, max-age=300",
            "X-Content-Type-Options": "nosniff",
        },
    )


def _file_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "file_not_found", "message": "文件不存在或你没有访问权限"},
    )
