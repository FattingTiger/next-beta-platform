from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any

from sqlalchemy.orm import Session

from beta_center.models import AuditLog, User

_REDACTED_KEYS = {
    "password",
    "current_password",
    "initial_password",
    "new_password",
    "password_hash",
    "token",
    "access_token",
    "refresh_token",
    "secret",
}
_REQUEST_ID: ContextVar[str] = ContextVar("audit_request_id", default="")


def bind_request_id(request_id: str) -> Token[str]:
    return _REQUEST_ID.set(request_id)


def reset_request_id(token: Token[str]) -> None:
    _REQUEST_ID.reset(token)


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: ("[REDACTED]" if key.lower() in _REDACTED_KEYS else _redact(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def record_audit(
    db: Session,
    *,
    actor: User | None,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    details: dict[str, Any] | None = None,
    request_ip: str = "",
    outcome: str = "success",
    reason_code: str = "",
) -> AuditLog:
    entry = AuditLog(
        actor_id=actor.id if actor else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=_redact(details or {}),
        request_ip=request_ip,
        outcome=outcome,
        reason_code=reason_code,
        request_id=_REQUEST_ID.get(),
    )
    db.add(entry)
    return entry
