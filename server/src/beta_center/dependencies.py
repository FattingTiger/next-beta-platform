from __future__ import annotations

import secrets
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address, ip_network
from typing import cast

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from beta_center.models import AuthSession, User, UserRole
from beta_center.runtime import Runtime
from beta_center.security import aware_utc, decode_access_token, is_expired, token_digest

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class Principal:
    user: User
    session: AuthSession
    via_cookie: bool


def get_runtime(request: Request) -> Runtime:
    return cast(Runtime, request.app.state.runtime)


async def get_db(runtime: Runtime = Depends(get_runtime)) -> AsyncGenerator[Session, None]:
    """Provide a capacity-bounded transactional Session.

    With ``scope="function"``, FastAPI keeps this generator open through the
    synchronous endpoint and response-model validation. Holding the database
    limiter across that whole interval ensures no more request Sessions are in
    flight than SQLAlchemy has connections. Excess requests wait asynchronously
    before reaching the worker pool. Cleanup also runs on the request task, so
    commit, rollback, and close cannot be starved by connection waiters.
    """
    async with runtime.database.request_limiter:
        db = runtime.database.session_factory()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


def request_ip(request: Request) -> str:
    peer = request.client.host if request.client else ""
    runtime = get_runtime(request)
    try:
        trusted_proxy = any(
            ip_address(peer) in ip_network(network, strict=False)
            for network in runtime.settings.trusted_proxy_networks
        )
    except ValueError:
        trusted_proxy = False
    if trusted_proxy:
        forwarded = request.headers.get("x-forwarded-for", "").split(",", maxsplit=1)[0].strip()
        try:
            return str(ip_address(forwarded)) if forwarded else peer[:64]
        except ValueError:
            return peer[:64]
    return peer[:64]


def get_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db, scope="function"),
    runtime: Runtime = Depends(get_runtime),
) -> Principal:
    principal = _resolve_principal(request, credentials, db, runtime)
    if principal is None:
        raise _not_authenticated()
    return principal


def get_optional_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db, scope="function"),
    runtime: Runtime = Depends(get_runtime),
) -> Principal | None:
    return _resolve_principal(request, credentials, db, runtime)


def _resolve_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
    db: Session,
    runtime: Runtime,
) -> Principal | None:
    via_cookie = credentials is None
    encoded = credentials.credentials if credentials else request.cookies.get("beta_access")
    if not encoded:
        return None
    try:
        claims = decode_access_token(encoded, runtime.settings)
    except ValueError:
        return None
    auth_session = db.get(AuthSession, claims.session_id)
    user = db.get(User, claims.user_id)
    if (
        auth_session is None
        or user is None
        or not user.is_active
        or auth_session.user_id != user.id
        or auth_session.revoked_at is not None
        or is_expired(auth_session.expires_at)
        or auth_session.generation != user.session_generation
        or claims.generation != user.session_generation
        or claims.role != user.role
    ):
        return None
    request.state.authenticated_user_id = user.id
    # Authentication and the synchronous endpoint are scheduled as separate
    # thread-pool calls. Release the read-only checkout between them so a burst
    # cannot fill every worker with requests waiting for the small DB pool while
    # earlier authenticated requests still hold all of its connections.
    # expire_on_commit=False keeps the principal fields usable and later endpoint
    # mutations are committed by the same request-scoped Session.
    db.commit()
    return Principal(user=user, session=auth_session, via_cookie=via_cookie)


def current_user(principal: Principal = Depends(get_principal)) -> User:
    return principal.user


def require_admin(principal: Principal = Depends(get_principal)) -> Principal:
    if principal.user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "password_change_required", "message": "首次登录必须先修改初始密码"},
        )
    if principal.user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "admin_required", "message": "需要管理员权限"},
        )
    return principal


def require_csrf(
    request: Request,
    principal: Principal = Depends(get_principal),
) -> Principal:
    if not principal.via_cookie:
        return principal
    header_token = request.headers.get("x-csrf-token", "")
    cookie_token = request.cookies.get("beta_csrf", "")
    if (
        not header_token
        or not cookie_token
        or not secrets.compare_digest(header_token, cookie_token)
        or not secrets.compare_digest(token_digest(header_token), principal.session.csrf_token_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "csrf_failed", "message": "页面安全校验已失效，请刷新后重试"},
        )
    return principal


def require_admin_csrf(
    request: Request,
    principal: Principal = Depends(require_csrf),
) -> Principal:
    if principal.user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "password_change_required", "message": "首次登录必须先修改初始密码"},
        )
    if principal.user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "admin_required", "message": "需要管理员权限"},
        )
    return principal


def require_recent_admin(
    principal: Principal = Depends(require_admin_csrf),
    runtime: Runtime = Depends(get_runtime),
) -> Principal:
    cutoff = datetime.now(UTC) - timedelta(minutes=runtime.settings.admin_reauth_minutes)
    if aware_utc(principal.session.reauthenticated_at) < cutoff:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "admin_reauthentication_required",
                "message": "该操作需要重新验证管理员密码",
            },
        )
    return principal


def require_ready_user(principal: Principal = Depends(get_principal)) -> Principal:
    if principal.user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "password_change_required", "message": "首次登录必须先修改初始密码"},
        )
    return principal


def _not_authenticated() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        headers={"WWW-Authenticate": "Bearer"},
        detail={"code": "not_authenticated", "message": "登录状态已失效，请重新登录"},
    )
