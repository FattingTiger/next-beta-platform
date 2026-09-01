from __future__ import annotations

import logging
import re
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from anyio.to_thread import current_default_thread_limiter
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from beta_center import __version__
from beta_center.config import Settings, get_settings
from beta_center.database import Database, check_database
from beta_center.dependencies import request_ip
from beta_center.models import User, UserRole
from beta_center.routers import (
    admin_apps,
    admin_bugs,
    admin_groups,
    admin_ops,
    admin_users,
    admin_web,
    apps,
    auth,
    bugs,
    downloads,
    files,
)
from beta_center.runtime import Runtime
from beta_center.security import LoginRateLimiter
from beta_center.services.apk import ApkInspector
from beta_center.services.audit import bind_request_id, record_audit, reset_request_id
from beta_center.services.storage import LocalStorage

logger = logging.getLogger("beta_center")
_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]+$")


def create_app(settings: Settings | None = None, *, runtime: Runtime | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    resolved_settings.ensure_runtime_directories()
    resolved_runtime = runtime or Runtime(
        settings=resolved_settings,
        database=Database(resolved_settings),
        storage=LocalStorage(resolved_settings.storage_root),
        apk_inspector=ApkInspector(
            apksigner_path=resolved_settings.apksigner_path,
            aapt_path=resolved_settings.aapt_path,
            timeout_seconds=resolved_settings.apk_tool_timeout_seconds,
            require_tools=resolved_settings.require_apk_tools,
        ),
        login_limiter=LoginRateLimiter(),
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        # Database work is synchronous. Keep worker concurrency bounded, but
        # leave one pool-width of headroom for health checks, dependencies, and
        # file responses while up to one pool-width waits for a connection.
        # get_db finalizes on the request task, so waiting workers cannot starve
        # the transaction cleanup that returns connections to the pool.
        thread_limiter = current_default_thread_limiter()
        previous_thread_tokens = thread_limiter.total_tokens
        database_capacity = resolved_settings.database_pool_size + resolved_settings.database_max_overflow
        thread_limiter.total_tokens = database_capacity * 2
        if resolved_settings.auto_create_schema:
            resolved_runtime.database.create_schema()
        try:
            yield
        finally:
            thread_limiter.total_tokens = previous_thread_tokens
            resolved_runtime.database.dispose()

    app = FastAPI(
        title="内测中心 API",
        version=__version__,
        docs_url="/api/docs" if resolved_settings.environment != "production" else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if resolved_settings.environment != "production" else None,
        lifespan=lifespan,
    )
    app.state.runtime = resolved_runtime
    web_root = Path(__file__).resolve().parent / "web"
    app.mount("/admin/assets", StaticFiles(directory=web_root), name="admin-assets")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=resolved_settings.allowed_hosts)
    app.middleware("http")(_security_headers)
    app.exception_handler(HTTPException)(_http_exception)
    app.exception_handler(StarletteHTTPException)(_http_exception)
    app.exception_handler(RequestValidationError)(_validation_exception)
    app.exception_handler(IntegrityError)(_integrity_exception)
    app.exception_handler(Exception)(_unexpected_exception)

    for router in (
        auth.router,
        apps.router,
        bugs.router,
        downloads.router,
        files.router,
        admin_users.router,
        admin_groups.router,
        admin_apps.router,
        admin_bugs.router,
        admin_ops.router,
        admin_web.router,
    ):
        app.include_router(router)

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse("/admin")

    @app.get("/health/live", tags=["health"])
    def health_live() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/health/ready", tags=["health"])
    def health_ready() -> JSONResponse:
        checks: dict[str, str] = {}
        ready = True
        try:
            check_database(resolved_runtime.database.engine)
            checks["database"] = "ok"
        except Exception:
            logger.exception("Database readiness check failed")
            checks["database"] = "failed"
            ready = False
        try:
            resolved_runtime.storage.verify_writable()
            checks["storage"] = "ok"
        except Exception:
            logger.exception("Storage readiness check failed")
            checks["storage"] = "failed"
        ready = ready and checks["storage"] == "ok"
        tools_available = resolved_runtime.apk_inspector.tools_available()
        checks["apk_tools"] = "ok" if tools_available else "missing"
        if resolved_settings.require_apk_tools and not tools_available:
            ready = False
        return JSONResponse(
            {"status": "ok" if ready else "not_ready", "checks": checks, "version": __version__},
            status_code=status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return app


async def _security_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
    supplied_request_id = request.headers.get("x-request-id", "")
    request_id = (
        supplied_request_id[:80]
        if supplied_request_id and _REQUEST_ID.fullmatch(supplied_request_id)
        else str(uuid.uuid4())
    )
    request.state.request_id = request_id
    audit_context = bind_request_id(request_id)
    try:
        try:
            response = await call_next(request)
        except IntegrityError as exc:
            response = await _integrity_exception(request, exc)
        except Exception as exc:
            # Starlette's outer server-error middleware would otherwise produce the
            # right body after this middleware has already been unwound, omitting
            # the security and correlation headers below.
            response = await _unexpected_exception(request, exc)
    finally:
        reset_request_id(audit_context)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data: blob:; style-src 'self'; "
        "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; "
        "form-action 'self'; object-src 'none'"
    )
    if request.app.state.runtime.settings.environment == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if request.url.path.startswith(("/api/", "/admin")):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


async def _http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
    code = str(detail.get("code", "request_failed"))
    message = str(detail.get("message", "请求处理失败"))
    _record_rejected_operation(request, code=code, response_status=exc.status_code)
    return JSONResponse(
        {
            "error": {
                "code": code,
                "message": message,
                "request_id": getattr(request.state, "request_id", None),
            }
        },
        status_code=exc.status_code,
        headers=exc.headers,
    )


async def _validation_exception(request: Request, exc: RequestValidationError) -> JSONResponse:
    fields = [".".join(str(part) for part in item["loc"] if part != "body") for item in exc.errors()]
    _record_rejected_operation(
        request,
        code="validation_error",
        response_status=status.HTTP_422_UNPROCESSABLE_CONTENT,
    )
    return JSONResponse(
        {
            "error": {
                "code": "validation_error",
                "message": "请求参数不完整或格式不正确",
                "fields": fields,
                "request_id": getattr(request.state, "request_id", None),
            }
        },
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
    )


async def _integrity_exception(request: Request, exc: IntegrityError) -> JSONResponse:
    logger.warning("Database constraint violation: %s", exc.orig)
    _record_rejected_operation(request, code="data_conflict", response_status=status.HTTP_409_CONFLICT)
    return JSONResponse(
        {
            "error": {
                "code": "data_conflict",
                "message": "数据已被其他操作修改，请刷新后重试",
                "request_id": getattr(request.state, "request_id", None),
            }
        },
        status_code=status.HTTP_409_CONFLICT,
    )


async def _unexpected_exception(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled request error", exc_info=exc)
    _record_rejected_operation(
        request,
        code="internal_error",
        response_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
    return JSONResponse(
        {
            "error": {
                "code": "internal_error",
                "message": "服务器暂时无法处理请求",
                "request_id": getattr(request.state, "request_id", None),
            }
        },
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def _record_rejected_operation(request: Request, *, code: str, response_status: int) -> None:
    path = request.url.path
    is_sensitive_write = request.method not in {"GET", "HEAD", "OPTIONS"} and (
        path.startswith("/api/v1/admin/")
        or path in {"/api/v1/auth/refresh", "/api/v1/auth/logout", "/api/v1/auth/logout-all"}
    )
    if not is_sensitive_write:
        return
    actor_id = getattr(request.state, "authenticated_user_id", None)
    if not actor_id:
        return
    try:
        runtime: Runtime = request.app.state.runtime
        with runtime.database.session() as db:
            actor = db.get(User, actor_id)
            if actor is None or (path.startswith("/api/v1/admin/") and actor.role != UserRole.ADMIN):
                return
            record_audit(
                db,
                actor=actor,
                action="security.request_rejected",
                entity_type="http_request",
                details={"method": request.method, "path": path, "status": response_status},
                request_ip=request_ip(request),
                outcome="failure",
                reason_code=code,
            )
    except Exception:
        logger.exception("Could not persist rejected-operation audit event")


app = create_app()
