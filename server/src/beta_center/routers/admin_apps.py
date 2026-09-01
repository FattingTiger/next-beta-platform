from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import delete as sql_delete
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload
from starlette.concurrency import run_in_threadpool

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
    App,
    AppScreenshot,
    AppStatus,
    AppVersion,
    Bug,
    DownloadRecord,
    TestGroup,
    VersionStatus,
)
from beta_center.presenters import app_detail, app_summary, version_summary
from beta_center.runtime import Runtime
from beta_center.schemas import (
    AppCreate,
    AppDetail,
    AppSummary,
    AppUpdate,
    Page,
    PermanentDeleteRequest,
    VersionPublishRequest,
    VersionSummary,
)
from beta_center.services.admin_confirmation import confirm_permanent_delete_password
from beta_center.services.apk import ApkInspection, ApkInspectionError
from beta_center.services.audit import record_audit
from beta_center.services.storage import StorageError

router = APIRouter(prefix="/api/v1/admin/apps", tags=["admin-apps"])
logger = logging.getLogger("beta_center.admin_apps")


@router.get("", response_model=Page[AppSummary])
def list_apps(
    search: str = Query(default="", max_length=100),
    app_status: AppStatus | None = Query(default=None, alias="status"),
    group_id: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db, scope="function"),
) -> Page[AppSummary]:
    query = select(App).options(selectinload(App.visible_groups), selectinload(App.versions))
    count_query = select(func.count(func.distinct(App.id))).select_from(App)
    if search:
        pattern = f"%{search.strip()}%"
        predicate = or_(App.name.ilike(pattern), App.package_name.ilike(pattern))
        query = query.where(predicate)
        count_query = count_query.where(predicate)
    if app_status is not None:
        query = query.where(App.status == app_status)
        count_query = count_query.where(App.status == app_status)
    if group_id:
        query = query.join(App.visible_groups).where(TestGroup.id == group_id)
        count_query = count_query.join(App.visible_groups).where(TestGroup.id == group_id)
    total = int(db.scalar(count_query) or 0)
    apps = db.scalars(
        query.order_by(App.updated_at.desc(), App.id.desc()).offset((page - 1) * page_size).limit(page_size)
    ).unique()
    return Page(items=[app_summary(db, app) for app in apps], total=total, page=page, page_size=page_size)


@router.post("", response_model=AppDetail, status_code=status.HTTP_201_CREATED)
def create_app(
    payload: AppCreate,
    request: Request,
    principal: Principal = Depends(require_recent_admin),
    db: Session = Depends(get_db, scope="function"),
) -> AppDetail:
    if db.scalar(select(App.id).where(App.package_name == payload.package_name)):
        raise _conflict("package_exists", "该应用包名已存在")
    app = App(
        name=payload.name,
        package_name=payload.package_name,
        short_description=payload.short_description,
        description=payload.description,
        visible_groups=_load_groups(db, payload.group_ids),
    )
    db.add(app)
    db.flush()
    record_audit(
        db,
        actor=principal.user,
        action="admin.app.create",
        entity_type="app",
        entity_id=app.id,
        details={"package_name": app.package_name, "group_ids": payload.group_ids},
        request_ip=request_ip(request),
    )
    return app_detail(db, app)


@router.get("/{app_id}", response_model=AppDetail)
def get_app(
    app_id: str,
    _principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db, scope="function"),
) -> AppDetail:
    return app_detail(db, _get_app(db, app_id))


@router.patch("/{app_id}", response_model=AppDetail)
def update_app(
    app_id: str,
    payload: AppUpdate,
    request: Request,
    principal: Principal = Depends(require_recent_admin),
    db: Session = Depends(get_db, scope="function"),
) -> AppDetail:
    app = _get_app(db, app_id, lock=True)
    changes = payload.model_dump(exclude_unset=True)
    if payload.name is not None:
        app.name = payload.name
    if payload.short_description is not None:
        app.short_description = payload.short_description
    if payload.description is not None:
        app.description = payload.description
    if payload.group_ids is not None:
        app.visible_groups = _load_groups(db, payload.group_ids)
    if payload.status is not None:
        if payload.status == AppStatus.PUBLISHED and app.status != AppStatus.PUBLISHED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "publish_version_required",
                    "message": "应用只能通过发布新的 APK 版本重新上架",
                },
            )
        app.status = payload.status
        if payload.status != AppStatus.PUBLISHED:
            for version in app.versions:
                version.download_enabled = False
    db.flush()
    record_audit(
        db,
        actor=principal.user,
        action="admin.app.update",
        entity_type="app",
        entity_id=app.id,
        details=changes,
        request_ip=request_ip(request),
    )
    return app_detail(db, app)


@router.delete("/{app_id}", status_code=status.HTTP_204_NO_CONTENT)
def permanently_delete_app(
    app_id: str,
    payload: PermanentDeleteRequest,
    request: Request,
    principal: Principal = Depends(require_admin_csrf),
    db: Session = Depends(get_db, scope="function"),
    runtime: Runtime = Depends(get_runtime),
) -> Response:
    app = _get_app(db, app_id, lock=True)
    if app.status != AppStatus.ARCHIVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "app_must_be_archived", "message": "应用必须先归档，才能永久删除"},
        )
    ip = request_ip(request)
    confirm_permanent_delete_password(
        db,
        runtime.settings,
        actor=principal.user,
        auth_session=principal.session,
        password=payload.current_password,
        request_ip=ip,
        action="admin.app.permanent_delete",
        entity_type="app",
        entity_id=app.id,
    )

    bugs = list(
        db.scalars(select(Bug).where(Bug.app_id == app.id).options(selectinload(Bug.attachments))).unique()
    )
    storage_keys = {
        key
        for key in (
            app.icon_storage_key,
            *(screenshot.storage_key for screenshot in app.screenshots),
            *(version.file_storage_key for version in app.versions),
            *(attachment.storage_key for bug in bugs for attachment in bug.attachments),
        )
        if key
    }
    app_name = app.name
    package_name = app.package_name
    version_count = len(app.versions)
    download_count = int(
        db.scalar(select(func.count(DownloadRecord.id)).where(DownloadRecord.app_id == app.id)) or 0
    )
    db.execute(sql_delete(DownloadRecord).where(DownloadRecord.app_id == app.id))
    for bug in bugs:
        db.delete(bug)
    db.flush()
    app.current_version_id = None
    db.flush()
    record_audit(
        db,
        actor=principal.user,
        action="admin.app.permanent_delete",
        entity_type="app",
        entity_id=app.id,
        details={
            "name": app_name,
            "package_name": package_name,
            "version_count": version_count,
            "bug_count": len(bugs),
            "download_count": download_count,
        },
        request_ip=ip,
    )
    db.delete(app)
    db.commit()
    _delete_storage_objects(runtime, storage_keys)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{app_id}/icon", response_model=AppDetail)
async def upload_icon(
    app_id: str,
    request: Request,
    file: UploadFile = File(...),
    principal: Principal = Depends(require_admin_csrf),
    db: Session = Depends(get_db, scope="function"),
    runtime: Runtime = Depends(get_runtime),
) -> AppDetail:
    _ensure_app_exists(db, app_id)
    try:
        stored = await runtime.storage.save_image(
            file,
            namespace="app-icons",
            max_bytes=runtime.settings.max_image_bytes,
            max_dimension=1024,
        )
    except StorageError as exc:
        raise _bad_upload(str(exc)) from exc
    app = _get_app(db, app_id, lock=True)
    old_key = app.icon_storage_key
    app.icon_storage_key = stored.key
    record_audit(
        db,
        actor=principal.user,
        action="admin.app.icon.upload",
        entity_type="app",
        entity_id=app.id,
        details={"sha256": stored.sha256, "bytes": stored.size},
        request_ip=request_ip(request),
    )
    try:
        db.commit()
    except Exception:
        runtime.storage.delete(stored.key)
        raise
    runtime.storage.delete(old_key)
    return app_detail(db, app)


@router.post("/{app_id}/screenshots", response_model=AppDetail)
async def upload_screenshot(
    app_id: str,
    request: Request,
    file: UploadFile = File(...),
    position: int | None = Form(default=None, ge=0, le=99),
    principal: Principal = Depends(require_admin_csrf),
    db: Session = Depends(get_db, scope="function"),
    runtime: Runtime = Depends(get_runtime),
) -> AppDetail:
    _ensure_app_exists(db, app_id)
    screenshot_count = db.scalar(select(func.count(AppScreenshot.id)).where(AppScreenshot.app_id == app_id))
    if int(screenshot_count or 0) >= 10:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "screenshot_limit", "message": "每个应用最多上传 10 张展示截图"},
        )
    try:
        stored = await runtime.storage.save_image(
            file,
            namespace="app-screenshots",
            max_bytes=runtime.settings.max_image_bytes,
        )
    except StorageError as exc:
        raise _bad_upload(str(exc)) from exc
    app = _get_app(db, app_id, lock=True)
    if len(app.screenshots) >= 10:
        runtime.storage.delete(stored.key)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "screenshot_limit", "message": "每个应用最多上传 10 张展示截图"},
        )
    target_position = min(position, len(app.screenshots)) if position is not None else len(app.screenshots)
    item = AppScreenshot(
        app_id=app.id,
        storage_key=stored.key,
        content_type=stored.content_type,
        position=target_position,
    )
    try:
        _open_screenshot_slot(db, app, target_position)
        db.add(item)
        db.flush()
        record_audit(
            db,
            actor=principal.user,
            action="admin.app.screenshot.upload",
            entity_type="app_screenshot",
            entity_id=item.id,
            details={"app_id": app.id, "position": target_position, "sha256": stored.sha256},
            request_ip=request_ip(request),
        )
        db.commit()
    except Exception:
        db.rollback()
        runtime.storage.delete(stored.key)
        raise
    db.refresh(app)
    return app_detail(db, _get_app(db, app.id))


@router.delete("/{app_id}/screenshots/{screenshot_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_screenshot(
    app_id: str,
    screenshot_id: str,
    request: Request,
    principal: Principal = Depends(require_admin_csrf),
    db: Session = Depends(get_db, scope="function"),
    runtime: Runtime = Depends(get_runtime),
) -> None:
    app = _get_app(db, app_id, lock=True)
    item = next((shot for shot in app.screenshots if shot.id == screenshot_id), None)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "screenshot_not_found", "message": "应用截图不存在"},
        )
    storage_key = item.storage_key
    deleted_position = item.position
    item_id = item.id
    db.delete(item)
    db.flush()
    _close_screenshot_slot(db, app, deleted_position, excluded_id=item_id)
    record_audit(
        db,
        actor=principal.user,
        action="admin.app.screenshot.delete",
        entity_type="app_screenshot",
        entity_id=item_id,
        details={"app_id": app.id},
        request_ip=request_ip(request),
    )
    db.commit()
    runtime.storage.delete(storage_key)


@router.post("/{app_id}/versions", response_model=VersionSummary, status_code=status.HTTP_201_CREATED)
async def upload_version(
    app_id: str,
    request: Request,
    file: UploadFile = File(...),
    release_notes: str = Form(default="", max_length=5000),
    publish: bool = Form(default=False),
    principal: Principal = Depends(require_admin_csrf),
    db: Session = Depends(get_db, scope="function"),
    runtime: Runtime = Depends(get_runtime),
) -> VersionSummary:
    if publish:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "separate_publish_required",
                "message": "APK 必须先完成上传校验，再由独立发布操作上线",
            },
        )
    app = _get_app(db, app_id)
    filename = _safe_original_filename(file.filename)
    if not filename.lower().endswith(".apk"):
        raise _bad_upload("上传文件必须是 APK")
    try:
        stored = await runtime.storage.save_upload(
            file,
            namespace="apks",
            extension=".apk",
            max_bytes=runtime.settings.max_apk_bytes,
            expected_content_types={
                "application/vnd.android.package-archive",
                "application/octet-stream",
                "application/zip",
            },
        )
        inspection = await run_in_threadpool(
            runtime.apk_inspector.inspect,
            runtime.storage.path_for(stored.key),
        )
    except (StorageError, ApkInspectionError) as exc:
        if "stored" in locals():
            runtime.storage.delete(stored.key)
        raise _bad_upload(str(exc)) from exc
    if inspection.package_name != app.package_name:
        runtime.storage.delete(stored.key)
        raise _bad_upload(f"APK 包名 {inspection.package_name} 与应用包名不一致")
    try:
        app = _get_app(db, app.id, lock=True)
        max_version_code = db.scalar(
            select(func.max(AppVersion.version_code)).where(AppVersion.app_id == app.id)
        )
        if max_version_code is not None and inspection.version_code <= max_version_code:
            raise _conflict("version_code_not_increasing", "新版本的 versionCode 必须大于历史版本")
        if app.signing_cert_sha256 and inspection.signing_cert_sha256 != app.signing_cert_sha256:
            raise _conflict("signing_certificate_changed", "APK 签名证书与已发布版本不一致")
        version = AppVersion(
            app_id=app.id,
            version_name=inspection.version_name,
            version_code=inspection.version_code,
            min_sdk=inspection.min_sdk,
            target_sdk=inspection.target_sdk,
            file_storage_key=stored.key,
            original_filename=filename,
            file_size=inspection.file_size,
            sha256=inspection.sha256,
            signing_cert_sha256=inspection.signing_cert_sha256,
            release_notes=release_notes.strip(),
            created_by_id=principal.user.id,
        )
        db.add(version)
        db.flush()
        record_audit(
            db,
            actor=principal.user,
            action="admin.version.upload",
            entity_type="app_version",
            entity_id=version.id,
            details={
                "app_id": app.id,
                "version_code": version.version_code,
                "sha256": version.sha256,
                "published": False,
            },
            request_ip=request_ip(request),
        )
        db.commit()
    except Exception:
        db.rollback()
        runtime.storage.delete(stored.key)
        raise
    return version_summary(version)


@router.post("/{app_id}/versions/{version_id}/publish", response_model=VersionSummary)
def publish_version(
    app_id: str,
    version_id: str,
    payload: VersionPublishRequest,
    request: Request,
    principal: Principal = Depends(require_recent_admin),
    db: Session = Depends(get_db, scope="function"),
    runtime: Runtime = Depends(get_runtime),
) -> VersionSummary:
    app = _get_app(db, app_id, lock=True)
    version = _get_version(db, app.id, version_id)
    if version.status != VersionStatus.DRAFT:
        raise _conflict("version_not_draft", "只有从未发布过的草稿版本可以发布")
    inspection = _inspect_stored_version(runtime, app, version)
    max_published_code = db.scalar(
        select(func.max(AppVersion.version_code)).where(
            AppVersion.app_id == app.id,
            AppVersion.status == VersionStatus.PUBLISHED,
        )
    )
    if max_published_code is not None and version.version_code <= max_published_code:
        raise _conflict("version_rollback_forbidden", "发布版本号必须高于所有历史已发布版本")
    if app.signing_cert_sha256:
        if not secrets.compare_digest(app.signing_cert_sha256, inspection.signing_cert_sha256):
            raise _conflict("signing_certificate_changed", "APK 签名证书与已发布版本不一致")
    else:
        app.signing_cert_sha256 = inspection.signing_cert_sha256
    version.release_notes = payload.release_notes
    _publish_version(db, app, version)
    record_audit(
        db,
        actor=principal.user,
        action="admin.version.publish",
        entity_type="app_version",
        entity_id=version.id,
        details={"app_id": app.id, "version_code": version.version_code},
        request_ip=request_ip(request),
    )
    db.flush()
    return version_summary(version)


@router.post("/{app_id}/versions/{version_id}/disable", response_model=VersionSummary)
def disable_version(
    app_id: str,
    version_id: str,
    request: Request,
    principal: Principal = Depends(require_recent_admin),
    db: Session = Depends(get_db, scope="function"),
) -> VersionSummary:
    app = _get_app(db, app_id, lock=True)
    version = _get_version(db, app.id, version_id)
    version.download_enabled = False
    version.status = VersionStatus.DISABLED
    if app.current_version_id == version.id:
        app.current_version_id = None
        app.status = AppStatus.DRAFT
    record_audit(
        db,
        actor=principal.user,
        action="admin.version.disable",
        entity_type="app_version",
        entity_id=version.id,
        details={"app_id": app.id},
        request_ip=request_ip(request),
    )
    return version_summary(version)


def _publish_version(db: Session, app: App, version: AppVersion) -> None:
    if app.current_version_id:
        current = next((item for item in app.versions if item.id == app.current_version_id), None)
        if current:
            current.download_enabled = False
            # The database enforces at most one enabled version per app. Flush
            # the old current row first so a single ORM flush cannot violate
            # the partial unique index while swapping versions.
            db.flush([current])
    version.status = VersionStatus.PUBLISHED
    version.download_enabled = True
    version.published_at = datetime.now(UTC)
    app.current_version_id = version.id
    app.status = AppStatus.PUBLISHED


def _inspect_stored_version(runtime: Runtime, app: App, version: AppVersion) -> ApkInspection:
    try:
        path = runtime.storage.path_for(version.file_storage_key)
        if not path.is_file():
            raise ApkInspectionError("APK 文件不存在")
        inspection = runtime.apk_inspector.inspect(path)
    except (StorageError, ApkInspectionError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "version_artifact_invalid", "message": f"版本文件校验失败：{exc}"},
        ) from exc
    metadata_matches = (
        inspection.package_name == app.package_name
        and inspection.version_name == version.version_name
        and inspection.version_code == version.version_code
        and inspection.file_size == version.file_size
        and secrets.compare_digest(inspection.sha256, version.sha256)
        and secrets.compare_digest(inspection.signing_cert_sha256, version.signing_cert_sha256)
    )
    if not metadata_matches:
        raise _conflict("version_artifact_changed", "APK 文件或解析信息已发生变化，禁止发布")
    return inspection


def _safe_original_filename(value: str | None) -> str:
    name = Path(value or "upload.apk").name
    cleaned = "".join(character for character in name if character.isalnum() or character in "-_.")[:180]
    return cleaned or "upload.apk"


def _open_screenshot_slot(db: Session, app: App, target_position: int) -> None:
    affected = [item for item in app.screenshots if item.position >= target_position]
    if not affected:
        return
    for item in affected:
        item.position += 100
    db.flush()
    for item in affected:
        item.position -= 99
    db.flush()


def _close_screenshot_slot(
    db: Session,
    app: App,
    deleted_position: int,
    *,
    excluded_id: str,
) -> None:
    affected = [
        item for item in app.screenshots if item.id != excluded_id and item.position > deleted_position
    ]
    if not affected:
        return
    for item in affected:
        item.position += 100
    db.flush()
    for item in affected:
        item.position -= 101
    db.flush()


def _get_app(db: Session, app_id: str, *, lock: bool = False) -> App:
    query = (
        select(App)
        .where(App.id == app_id)
        .options(
            selectinload(App.visible_groups),
            selectinload(App.versions),
            selectinload(App.screenshots),
        )
    )
    if lock:
        query = query.with_for_update()
    app = db.scalar(query)
    if app is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "app_not_found", "message": "应用不存在"},
        )
    return app


def _ensure_app_exists(db: Session, app_id: str) -> None:
    if db.scalar(select(App.id).where(App.id == app_id)) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "app_not_found", "message": "应用不存在"},
        )


def _get_version(db: Session, app_id: str, version_id: str) -> AppVersion:
    version = db.scalar(select(AppVersion).where(AppVersion.id == version_id, AppVersion.app_id == app_id))
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "version_not_found", "message": "应用版本不存在"},
        )
    return version


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


def _delete_storage_objects(runtime: Runtime, storage_keys: set[str]) -> None:
    for storage_key in storage_keys:
        try:
            runtime.storage.delete(storage_key)
        except (OSError, StorageError):
            logger.exception("Could not remove permanently deleted app object %s", storage_key)


def _bad_upload(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={"code": "invalid_upload", "message": message},
    )


def _conflict(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": code, "message": message})
