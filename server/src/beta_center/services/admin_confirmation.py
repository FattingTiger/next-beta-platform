from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from beta_center.config import Settings
from beta_center.models import AuthSession, User
from beta_center.security import (
    admin_reauth_attempt_allowed,
    clear_admin_reauth_identity,
    record_admin_reauth_failure,
    verify_password,
)
from beta_center.services.audit import record_audit


def confirm_permanent_delete_password(
    db: Session,
    settings: Settings,
    *,
    actor: User,
    auth_session: AuthSession,
    password: str,
    request_ip: str,
    action: str,
    entity_type: str,
    entity_id: str,
) -> None:
    """Require a fresh password value for every irreversible deletion.

    This deliberately does not rely on the session's recent reauthentication
    timestamp: a caller must submit the current password with each request.
    """
    now = datetime.now(UTC)
    if not admin_reauth_attempt_allowed(
        db,
        settings,
        session_id=auth_session.id,
        user_id=actor.id,
        request_ip=request_ip,
        now=now,
    ):
        record_audit(
            db,
            actor=actor,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            request_ip=request_ip,
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
            headers={"Retry-After": str(settings.admin_reauth_lock_minutes * 60)},
        )
    if not verify_password(password, actor.password_hash):
        record_admin_reauth_failure(
            db,
            settings,
            session_id=auth_session.id,
            user_id=actor.id,
            request_ip=request_ip,
            now=now,
        )
        record_audit(
            db,
            actor=actor,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            request_ip=request_ip,
            outcome="failure",
            reason_code="invalid_password",
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "current_password_invalid", "message": "当前管理员密码不正确"},
        )
    clear_admin_reauth_identity(
        db,
        settings,
        session_id=auth_session.id,
        user_id=actor.id,
    )
