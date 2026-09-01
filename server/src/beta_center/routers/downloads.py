from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from beta_center.dependencies import (
    Principal,
    get_db,
    get_optional_principal,
    get_runtime,
    request_ip,
    require_csrf,
)
from beta_center.models import App, AppVersion, DownloadRecord, DownloadStatus, User, VersionStatus
from beta_center.runtime import Runtime
from beta_center.schemas import (
    DownloadCompleteRequest,
    DownloadFailureRequest,
    DownloadStartRequest,
    DownloadTicket,
)
from beta_center.security import is_expired, random_token, token_digest
from beta_center.services.access import user_can_access_app

router = APIRouter(prefix="/api/v1/downloads", tags=["downloads"])


@router.post("", response_model=DownloadTicket, status_code=status.HTTP_201_CREATED)
def start_download(
    payload: DownloadStartRequest,
    request: Request,
    principal: Principal = Depends(require_csrf),
    db: Session = Depends(get_db, scope="function"),
    runtime: Runtime = Depends(get_runtime),
) -> DownloadTicket:
    if principal.user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "password_change_required", "message": "首次登录必须先修改初始密码"},
        )
    version = db.get(AppVersion, payload.version_id)
    if version is None:
        raise _download_unavailable()
    app = db.get(App, version.app_id)
    if (
        app is None
        or app.current_version_id != version.id
        or version.status != VersionStatus.PUBLISHED
        or not version.download_enabled
        or not user_can_access_app(db, principal.user, app.id)
    ):
        raise _download_unavailable()
    ticket = random_token()
    expires_at = datetime.now(UTC) + timedelta(minutes=runtime.settings.download_ticket_minutes)
    db.scalar(select(User.id).where(User.id == principal.user.id).with_for_update())
    record = db.scalar(
        select(DownloadRecord).where(
            DownloadRecord.user_id == principal.user.id,
            DownloadRecord.client_request_id == payload.client_request_id,
        )
    )
    if record is not None and (record.app_id != app.id or record.version_id != version.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "download_idempotency_conflict",
                "message": "该请求标识已用于另一个应用版本",
            },
        )
    if record is not None and record.status == DownloadStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "download_already_completed", "message": "该下载请求已经完成"},
        )
    if record is None:
        record = DownloadRecord(
            user_id=principal.user.id,
            app_id=app.id,
            version_id=version.id,
            client_request_id=payload.client_request_id,
            ticket_hash=token_digest(ticket),
            ticket_expires_at=expires_at,
        )
        db.add(record)
    else:
        record.status = DownloadStatus.STARTED
        record.ticket_hash = token_digest(ticket)
        record.ticket_expires_at = expires_at
        record.bytes_sent = 0
        record.completed_at = None
        record.failure_reason = ""
    record.device_model = payload.device_model
    record.android_version = payload.android_version
    record.client_version = payload.client_version
    record.request_ip = request_ip(request)
    record.user_agent = request.headers.get("user-agent", "")[:300]
    db.flush()
    return DownloadTicket(
        download_id=record.id,
        client_request_id=record.client_request_id,
        ticket=ticket,
        url=f"/api/v1/downloads/{record.id}/file?ticket={quote(ticket)}",
        expires_at=expires_at,
        file_size=version.file_size,
        sha256=version.sha256,
        filename=_safe_download_name(app.name, version.version_name),
    )


@router.get("/{download_id}/file", response_class=FileResponse)
def download_file(
    download_id: str,
    ticket: str = Query(min_length=20, max_length=500),
    principal: Principal | None = Depends(get_optional_principal),
    db: Session = Depends(get_db, scope="function"),
    runtime: Runtime = Depends(get_runtime),
) -> Response:
    record = db.get(DownloadRecord, download_id)
    if (
        principal is None
        or principal.user.must_change_password
        or record is None
        or record.user_id != principal.user.id
        or record.ticket_hash != token_digest(ticket)
        or is_expired(record.ticket_expires_at)
        or record.status not in {DownloadStatus.STARTED, DownloadStatus.FAILED}
    ):
        raise _download_unavailable()
    assert principal is not None
    user = principal.user
    app = db.get(App, record.app_id)
    version = db.get(AppVersion, record.version_id)
    if (
        not user.is_active
        or app is None
        or version is None
        or app.current_version_id != version.id
        or not version.download_enabled
        or not user_can_access_app(db, user, app.id)
    ):
        raise _download_unavailable()
    path = runtime.storage.path_for(version.file_storage_key)
    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "apk_missing", "message": "APK 文件暂时不可用，请联系管理员"},
        )
    record.status = DownloadStatus.STARTED
    db.flush()
    safe_name = _safe_download_name(app.name, version.version_name)
    common_headers = {
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
        "Content-Disposition": _content_disposition(safe_name),
    }
    if runtime.settings.use_x_accel_redirect:
        return Response(
            status_code=status.HTTP_200_OK,
            media_type="application/vnd.android.package-archive",
            headers={
                **common_headers,
                "X-Accel-Redirect": f"/_protected-files/{quote(version.file_storage_key, safe='/')}",
            },
        )
    return FileResponse(
        path,
        media_type="application/vnd.android.package-archive",
        filename=safe_name,
        headers={**common_headers, "Accept-Ranges": "bytes"},
    )


@router.post("/{download_id}/complete", status_code=status.HTTP_204_NO_CONTENT)
def complete_download(
    download_id: str,
    payload: DownloadCompleteRequest,
    principal: Principal = Depends(require_csrf),
    db: Session = Depends(get_db, scope="function"),
) -> None:
    record = _owned_record(db, download_id, principal, lock=True)
    version = db.get(AppVersion, record.version_id)
    if version is None or payload.sha256 != version.sha256 or payload.bytes_received != version.file_size:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "download_integrity_failed", "message": "下载文件大小或摘要校验失败"},
        )
    if record.status == DownloadStatus.COMPLETED:
        return
    if record.status != DownloadStatus.STARTED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "download_not_active", "message": "该下载已结束，不能确认完成"},
        )
    record.status = DownloadStatus.COMPLETED
    record.bytes_sent = payload.bytes_received
    record.completed_at = datetime.now(UTC)
    record.failure_reason = ""
    db.flush()


@router.post("/{download_id}/failure", status_code=status.HTTP_204_NO_CONTENT)
def mark_download_failure(
    download_id: str,
    payload: DownloadFailureRequest,
    principal: Principal = Depends(require_csrf),
    db: Session = Depends(get_db, scope="function"),
) -> None:
    record = _owned_record(db, download_id, principal, lock=True)
    if record.status == DownloadStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "download_already_completed", "message": "已完成的下载不能改为失败"},
        )
    if record.status != DownloadStatus.STARTED:
        if record.status == payload.status and record.failure_reason == payload.reason:
            return
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "download_already_ended", "message": "该下载已记录结束状态"},
        )
    record.status = payload.status
    record.failure_reason = payload.reason
    db.flush()


def _owned_record(
    db: Session,
    download_id: str,
    principal: Principal,
    *,
    lock: bool = False,
) -> DownloadRecord:
    query = select(DownloadRecord).where(
        DownloadRecord.id == download_id,
        DownloadRecord.user_id == principal.user.id,
    )
    if lock:
        query = query.with_for_update()
    record = db.scalar(query)
    if record is None:
        raise _download_unavailable()
    return record


def _safe_download_name(app_name: str, version_name: str) -> str:
    def clean(value: str) -> str:
        return "".join(character for character in value if character.isalnum() or character in "-_.")[:80]

    safe_app = clean(app_name) or "beta-app"
    safe_version = clean(version_name) or "version"
    return f"{safe_app}-{safe_version}.apk"


def _content_disposition(filename: str) -> str:
    # Header values must remain Latin-1 encodable. RFC 5987 carries the real
    # UTF-8 name while the ASCII fallback keeps older download clients happy.
    encoded = quote(filename, safe="")
    return f"attachment; filename=beta-app.apk; filename*=UTF-8''{encoded}"


def _download_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "download_unavailable", "message": "下载不存在、已过期或你没有访问权限"},
    )
