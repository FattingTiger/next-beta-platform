from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from beta_center.dependencies import (
    Principal,
    current_user,
    get_db,
    get_runtime,
    request_ip,
    require_admin_csrf,
    require_csrf,
    require_ready_user,
)
from beta_center.models import AuthSession, User, utc_now
from beta_center.presenters import user_summary
from beta_center.runtime import Runtime
from beta_center.schemas import (
    AuthResponse,
    ChangePasswordRequest,
    LoginRequest,
    ReauthenticateRequest,
    RefreshRequest,
    UserSummary,
)
from beta_center.security import (
    admin_reauth_attempt_allowed,
    aware_utc,
    clear_admin_reauth_identity,
    clear_login_identity,
    clear_password_change_identity,
    consume_dummy_password_check,
    create_access_token,
    hash_password,
    is_expired,
    login_attempt_allowed,
    normalize_phone,
    password_change_attempt_allowed,
    password_needs_rehash,
    random_token,
    record_admin_reauth_failure,
    record_login_failure,
    record_password_change_failure,
    token_digest,
    verify_password,
)
from beta_center.services.audit import record_audit

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=AuthResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db, scope="function"),
    runtime: Runtime = Depends(get_runtime),
) -> AuthResponse:
    now = datetime.now(UTC)
    ip = request_ip(request)
    phone = normalize_phone(payload.phone)
    if not login_attempt_allowed(
        db,
        runtime.settings,
        request_ip=ip,
        identity=phone,
        now=now,
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "login_rate_limited", "message": "登录尝试过于频繁，请稍后再试"},
            headers={"Retry-After": str(runtime.settings.login_lock_minutes * 60)},
        )
    user = db.scalar(select(User).where(User.phone == phone).with_for_update())
    if user is None:
        consume_dummy_password_check(payload.password)
        record_login_failure(
            db,
            runtime.settings,
            request_ip=ip,
            identity=phone,
            now=now,
        )
        record_audit(
            db,
            actor=None,
            action="auth.login",
            entity_type="user",
            details={"phone_suffix": phone[-4:]},
            request_ip=ip,
            outcome="failure",
            reason_code="invalid_credentials",
        )
        db.commit()
        raise _invalid_credentials()
    if user.locked_until and aware_utc(user.locked_until) > now:
        record_audit(
            db,
            actor=user,
            action="auth.login",
            entity_type="user",
            entity_id=user.id,
            request_ip=ip,
            outcome="locked",
            reason_code="account_locked",
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "login_locked", "message": "登录尝试过于频繁，请稍后再试"},
            headers={"Retry-After": str(runtime.settings.login_lock_minutes * 60)},
        )
    password_valid = verify_password(payload.password, user.password_hash)
    if not user.is_active or not password_valid:
        record_login_failure(
            db,
            runtime.settings,
            request_ip=ip,
            identity=phone,
            now=now,
        )
        user.failed_login_count += 1
        if user.failed_login_count >= runtime.settings.login_failure_limit:
            user.locked_until = now + timedelta(minutes=runtime.settings.login_lock_minutes)
            user.failed_login_count = 0
        record_audit(
            db,
            actor=user,
            action="auth.login",
            entity_type="user",
            entity_id=user.id,
            request_ip=ip,
            outcome="failure",
            reason_code="account_inactive" if not user.is_active else "invalid_credentials",
        )
        db.commit()
        raise _invalid_credentials()
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    clear_login_identity(db, runtime.settings, phone)
    auth_response = _create_session(db, user=user, request=request, runtime=runtime)
    _set_auth_cookies(response, auth_response, runtime)
    record_audit(
        db,
        actor=user,
        action="auth.login",
        entity_type="session",
        request_ip=ip,
        details={"client_name": payload.client_name},
    )
    db.flush()
    return auth_response


@router.post("/refresh", response_model=AuthResponse)
def refresh(
    payload: RefreshRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db, scope="function"),
    runtime: Runtime = Depends(get_runtime),
) -> AuthResponse:
    supplied = payload.refresh_token or request.cookies.get("beta_refresh")
    if not supplied:
        raise _invalid_refresh()
    auth_session = db.scalar(
        select(AuthSession).where(AuthSession.refresh_token_hash == token_digest(supplied)).with_for_update()
    )
    if auth_session is None:
        raise _invalid_refresh()
    if payload.refresh_token is None:
        _require_refresh_csrf(request, auth_session)
    user = db.get(User, auth_session.user_id)
    if (
        user is None
        or not user.is_active
        or auth_session.revoked_at is not None
        or is_expired(auth_session.expires_at)
        or auth_session.generation != user.session_generation
    ):
        if auth_session.revoked_at is None:
            auth_session.revoked_at = utc_now()
        raise _invalid_refresh()
    refresh_token = random_token()
    csrf_token = random_token(32)
    auth_session.refresh_token_hash = token_digest(refresh_token)
    auth_session.csrf_token_hash = token_digest(csrf_token)
    auth_session.last_used_at = utc_now()
    access_token, expires_at = create_access_token(user, auth_session.id, runtime.settings)
    result = AuthResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
        csrf_token=csrf_token,
        user=user_summary(user),
    )
    _set_auth_cookies(response, result, runtime)
    record_audit(
        db,
        actor=user,
        action="auth.refresh",
        entity_type="session",
        entity_id=auth_session.id,
        request_ip=request_ip(request),
    )
    db.flush()
    return result


@router.get("/me", response_model=UserSummary)
def me(user: User = Depends(current_user)) -> UserSummary:
    return user_summary(user)


@router.get("/upload-permission/admin", include_in_schema=False, status_code=status.HTTP_204_NO_CONTENT)
def admin_upload_permission(_principal: Principal = Depends(require_admin_csrf)) -> Response:
    """Small auth subrequest used by Nginx before it accepts an upload body."""
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/upload-permission/user", include_in_schema=False, status_code=status.HTTP_204_NO_CONTENT)
def user_upload_permission(_principal: Principal = Depends(require_ready_user)) -> Response:
    """Authenticate Bug reporters before Nginx streams multipart bytes."""
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    request: Request,
    principal: Principal = Depends(require_csrf),
    db: Session = Depends(get_db, scope="function"),
    runtime: Runtime = Depends(get_runtime),
) -> Response:
    principal.session.revoked_at = utc_now()
    record_audit(
        db,
        actor=principal.user,
        action="auth.logout",
        entity_type="session",
        entity_id=principal.session.id,
        request_ip=request_ip(request),
    )
    db.flush()
    _clear_auth_cookies(response, runtime)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
def logout_all(
    response: Response,
    request: Request,
    principal: Principal = Depends(require_csrf),
    db: Session = Depends(get_db, scope="function"),
    runtime: Runtime = Depends(get_runtime),
) -> Response:
    principal.user.session_generation += 1
    db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == principal.user.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=utc_now())
    )
    record_audit(
        db,
        actor=principal.user,
        action="auth.logout_all",
        entity_type="user",
        entity_id=principal.user.id,
        request_ip=request_ip(request),
    )
    db.flush()
    _clear_auth_cookies(response, runtime)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: ChangePasswordRequest,
    response: Response,
    request: Request,
    principal: Principal = Depends(require_csrf),
    db: Session = Depends(get_db, scope="function"),
    runtime: Runtime = Depends(get_runtime),
) -> Response:
    now = datetime.now(UTC)
    ip = request_ip(request)
    if not password_change_attempt_allowed(
        db,
        runtime.settings,
        session_id=principal.session.id,
        user_id=principal.user.id,
        request_ip=ip,
        now=now,
    ):
        record_audit(
            db,
            actor=principal.user,
            action="auth.change_password",
            entity_type="session",
            entity_id=principal.session.id,
            request_ip=ip,
            outcome="locked",
            reason_code="password_change_rate_limited",
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "password_change_rate_limited",
                "message": "当前密码验证尝试过于频繁，请稍后再试",
            },
            headers={"Retry-After": str(runtime.settings.password_change_lock_minutes * 60)},
        )
    if not verify_password(payload.current_password, principal.user.password_hash):
        record_password_change_failure(
            db,
            runtime.settings,
            session_id=principal.session.id,
            user_id=principal.user.id,
            request_ip=ip,
            now=now,
        )
        record_audit(
            db,
            actor=principal.user,
            action="auth.change_password",
            entity_type="session",
            entity_id=principal.session.id,
            request_ip=ip,
            outcome="failure",
            reason_code="invalid_password",
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "current_password_invalid", "message": "当前密码不正确"},
        )
    clear_password_change_identity(
        db,
        runtime.settings,
        session_id=principal.session.id,
        user_id=principal.user.id,
    )
    principal.user.password_hash = hash_password(payload.new_password)
    principal.user.must_change_password = False
    principal.user.session_generation += 1
    db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == principal.user.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=utc_now())
    )
    record_audit(
        db,
        actor=principal.user,
        action="auth.change_password",
        entity_type="user",
        entity_id=principal.user.id,
        request_ip=ip,
    )
    db.flush()
    _clear_auth_cookies(response, runtime)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/reauthenticate", status_code=status.HTTP_204_NO_CONTENT)
def reauthenticate(
    payload: ReauthenticateRequest,
    request: Request,
    principal: Principal = Depends(require_admin_csrf),
    db: Session = Depends(get_db, scope="function"),
    runtime: Runtime = Depends(get_runtime),
) -> Response:
    now = datetime.now(UTC)
    ip = request_ip(request)
    if not admin_reauth_attempt_allowed(
        db,
        runtime.settings,
        session_id=principal.session.id,
        user_id=principal.user.id,
        request_ip=ip,
        now=now,
    ):
        record_audit(
            db,
            actor=principal.user,
            action="auth.reauthenticate",
            entity_type="session",
            entity_id=principal.session.id,
            request_ip=ip,
            outcome="locked",
            reason_code="admin_reauth_rate_limited",
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "admin_reauth_rate_limited",
                "message": "管理员密码验证尝试过于频繁，请稍后再试",
            },
            headers={"Retry-After": str(runtime.settings.admin_reauth_lock_minutes * 60)},
        )
    if not verify_password(payload.password, principal.user.password_hash):
        record_admin_reauth_failure(
            db,
            runtime.settings,
            session_id=principal.session.id,
            user_id=principal.user.id,
            request_ip=ip,
            now=now,
        )
        record_audit(
            db,
            actor=principal.user,
            action="auth.reauthenticate",
            entity_type="session",
            entity_id=principal.session.id,
            request_ip=ip,
            outcome="failure",
            reason_code="invalid_password",
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "current_password_invalid", "message": "当前密码不正确"},
        )
    clear_admin_reauth_identity(
        db,
        runtime.settings,
        session_id=principal.session.id,
        user_id=principal.user.id,
    )
    principal.session.reauthenticated_at = now
    record_audit(
        db,
        actor=principal.user,
        action="auth.reauthenticate",
        entity_type="session",
        entity_id=principal.session.id,
        request_ip=ip,
    )
    db.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _create_session(db: Session, *, user: User, request: Request, runtime: Runtime) -> AuthResponse:
    refresh_token = random_token()
    csrf_token = random_token(32)
    now = datetime.now(UTC)
    auth_session = AuthSession(
        user_id=user.id,
        refresh_token_hash=token_digest(refresh_token),
        csrf_token_hash=token_digest(csrf_token),
        generation=user.session_generation,
        user_agent=request.headers.get("user-agent", "")[:300],
        request_ip=request_ip(request),
        expires_at=now + timedelta(days=runtime.settings.refresh_token_days),
        reauthenticated_at=now,
    )
    db.add(auth_session)
    db.flush()
    access_token, expires_at = create_access_token(user, auth_session.id, runtime.settings)
    return AuthResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
        csrf_token=csrf_token,
        user=user_summary(user),
    )


def _set_auth_cookies(response: Response, result: AuthResponse, runtime: Runtime) -> None:
    response.set_cookie(
        "beta_access",
        result.access_token,
        httponly=True,
        max_age=runtime.settings.access_token_minutes * 60,
        path="/",
        secure=runtime.settings.cookie_secure,
        samesite="strict",
        domain=runtime.settings.cookie_domain,
    )
    response.set_cookie(
        "beta_refresh",
        result.refresh_token,
        httponly=True,
        max_age=runtime.settings.refresh_token_days * 86_400,
        path="/api/v1/auth",
        secure=runtime.settings.cookie_secure,
        samesite="strict",
        domain=runtime.settings.cookie_domain,
    )
    response.set_cookie(
        "beta_csrf",
        result.csrf_token,
        httponly=False,
        max_age=runtime.settings.refresh_token_days * 86_400,
        path="/",
        secure=runtime.settings.cookie_secure,
        samesite="strict",
        domain=runtime.settings.cookie_domain,
    )


def _clear_auth_cookies(response: Response, runtime: Runtime) -> None:
    response.delete_cookie("beta_access", path="/", domain=runtime.settings.cookie_domain)
    response.delete_cookie(
        "beta_refresh",
        path="/api/v1/auth",
        domain=runtime.settings.cookie_domain,
    )
    response.delete_cookie("beta_csrf", path="/", domain=runtime.settings.cookie_domain)


def _require_refresh_csrf(request: Request, auth_session: AuthSession) -> None:
    header_token = request.headers.get("x-csrf-token", "")
    cookie_token = request.cookies.get("beta_csrf", "")
    if (
        not header_token
        or not cookie_token
        or not secrets.compare_digest(header_token, cookie_token)
        or not secrets.compare_digest(token_digest(header_token), auth_session.csrf_token_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "csrf_failed", "message": "页面安全校验已失效，请刷新后重试"},
        )


def _invalid_credentials() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "invalid_credentials", "message": "手机号或密码不正确"},
    )


def _invalid_refresh() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "invalid_refresh", "message": "登录状态已失效，请重新登录"},
    )
