from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import threading
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from beta_center.config import Settings
from beta_center.models import AuthThrottle, User, UserRole

_PHONE_SEPARATORS = re.compile(r"[\s()-]")
_PHONE_PATTERN = re.compile(r"^\+?[0-9]{7,20}$")
_PASSWORD_HASHER = PasswordHasher(time_cost=3, memory_cost=65_536, parallelism=4)
_DUMMY_PASSWORD_HASH = _PASSWORD_HASHER.hash("Dummy-Only-For-Timing-9!")


class InvalidTokenError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AccessClaims:
    user_id: str
    session_id: str
    generation: int
    role: UserRole
    expires_at: datetime


class LoginRateLimiter:
    def __init__(
        self,
        *,
        window_seconds: int = 900,
        max_per_ip: int = 30,
        max_per_identity: int = 10,
    ) -> None:
        self.window_seconds = window_seconds
        self.max_per_ip = max_per_ip
        self.max_per_identity = max_per_identity
        self._entries: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check_and_record(self, *, request_ip: str, identity: str, now_timestamp: float) -> bool:
        keys = ((f"ip:{request_ip}", self.max_per_ip), (f"identity:{identity}", self.max_per_identity))
        cutoff = now_timestamp - self.window_seconds
        with self._lock:
            for key, _limit in keys:
                entries = self._entries[key]
                while entries and entries[0] <= cutoff:
                    entries.popleft()
            if any(len(self._entries[key]) >= limit for key, limit in keys):
                return False
            for key, _limit in keys:
                self._entries[key].append(now_timestamp)
        return True

    def clear_identity(self, identity: str) -> None:
        with self._lock:
            self._entries.pop(f"identity:{identity}", None)

    def clear_ip(self, request_ip: str) -> None:
        with self._lock:
            self._entries.pop(f"ip:{request_ip}", None)


def login_attempt_allowed(
    db: Session,
    settings: Settings,
    *,
    request_ip: str,
    identity: str,
    now: datetime,
) -> bool:
    return _throttle_attempt_allowed(
        db,
        settings,
        factors=(
            ("ip", request_ip, settings.login_ip_failure_limit),
            ("identity", identity, settings.login_identity_failure_limit),
        ),
        now=now,
        window_minutes=settings.login_rate_window_minutes,
    )


def record_login_failure(
    db: Session,
    settings: Settings,
    *,
    request_ip: str,
    identity: str,
    now: datetime,
) -> None:
    _record_throttle_failure(
        db,
        settings,
        factors=(
            ("ip", request_ip, settings.login_ip_failure_limit),
            ("identity", identity, settings.login_identity_failure_limit),
        ),
        now=now,
        window_minutes=settings.login_rate_window_minutes,
    )


def clear_login_identity(db: Session, settings: Settings, identity: str) -> None:
    db.execute(
        delete(AuthThrottle).where(AuthThrottle.key_hash == _throttle_key(settings, "identity", identity))
    )


def admin_reauth_attempt_allowed(
    db: Session,
    settings: Settings,
    *,
    session_id: str,
    user_id: str,
    request_ip: str,
    now: datetime,
) -> bool:
    return _throttle_attempt_allowed(
        db,
        settings,
        factors=_admin_reauth_factors(settings, session_id, user_id, request_ip),
        now=now,
        window_minutes=settings.admin_reauth_lock_minutes,
    )


def record_admin_reauth_failure(
    db: Session,
    settings: Settings,
    *,
    session_id: str,
    user_id: str,
    request_ip: str,
    now: datetime,
) -> None:
    _record_throttle_failure(
        db,
        settings,
        factors=_admin_reauth_factors(settings, session_id, user_id, request_ip),
        now=now,
        window_minutes=settings.admin_reauth_lock_minutes,
    )


def clear_admin_reauth_identity(
    db: Session,
    settings: Settings,
    *,
    session_id: str,
    user_id: str,
) -> None:
    keys = (
        _throttle_key(settings, "admin_reauth_session", session_id),
        _throttle_key(settings, "admin_reauth_user", user_id),
    )
    db.execute(delete(AuthThrottle).where(AuthThrottle.key_hash.in_(keys)))


def password_change_attempt_allowed(
    db: Session,
    settings: Settings,
    *,
    session_id: str,
    user_id: str,
    request_ip: str,
    now: datetime,
) -> bool:
    return _throttle_attempt_allowed(
        db,
        settings,
        factors=_password_change_factors(settings, session_id, user_id, request_ip),
        now=now,
        window_minutes=settings.password_change_lock_minutes,
    )


def record_password_change_failure(
    db: Session,
    settings: Settings,
    *,
    session_id: str,
    user_id: str,
    request_ip: str,
    now: datetime,
) -> None:
    _record_throttle_failure(
        db,
        settings,
        factors=_password_change_factors(settings, session_id, user_id, request_ip),
        now=now,
        window_minutes=settings.password_change_lock_minutes,
    )


def clear_password_change_identity(
    db: Session,
    settings: Settings,
    *,
    session_id: str,
    user_id: str,
) -> None:
    keys = (
        _throttle_key(settings, "pwd_change_session", session_id),
        _throttle_key(settings, "pwd_change_user", user_id),
    )
    db.execute(delete(AuthThrottle).where(AuthThrottle.key_hash.in_(keys)))


def _admin_reauth_factors(
    settings: Settings,
    session_id: str,
    user_id: str,
    request_ip: str,
) -> tuple[tuple[str, str, int], ...]:
    return (
        ("admin_reauth_session", session_id, settings.admin_reauth_session_failure_limit),
        ("admin_reauth_user", user_id, settings.admin_reauth_user_failure_limit),
        ("admin_reauth_ip", request_ip, settings.admin_reauth_ip_failure_limit),
    )


def _password_change_factors(
    settings: Settings,
    session_id: str,
    user_id: str,
    request_ip: str,
) -> tuple[tuple[str, str, int], ...]:
    return (
        ("pwd_change_session", session_id, settings.password_change_session_failure_limit),
        ("pwd_change_user", user_id, settings.password_change_user_failure_limit),
        ("pwd_change_ip", request_ip, settings.password_change_ip_failure_limit),
    )


def _throttle_attempt_allowed(
    db: Session,
    settings: Settings,
    *,
    factors: tuple[tuple[str, str, int], ...],
    now: datetime,
    window_minutes: int,
) -> bool:
    rows = _locked_throttle_rows(db, settings, factors=factors, now=now)
    window = timedelta(minutes=window_minutes)
    allowed = True
    for row, _limit in rows:
        if aware_utc(row.window_started_at) + window <= now:
            row.failure_count = 0
            row.window_started_at = now
            row.locked_until = None
        if row.locked_until and aware_utc(row.locked_until) > now:
            allowed = False
        row.updated_at = now
    return allowed


def _record_throttle_failure(
    db: Session,
    settings: Settings,
    *,
    factors: tuple[tuple[str, str, int], ...],
    now: datetime,
    window_minutes: int,
) -> None:
    rows = _locked_throttle_rows(db, settings, factors=factors, now=now)
    window = timedelta(minutes=window_minutes)
    for row, limit in rows:
        if aware_utc(row.window_started_at) + window <= now:
            row.failure_count = 0
            row.window_started_at = now
            row.locked_until = None
        row.failure_count += 1
        if row.failure_count >= limit:
            row.locked_until = now + window
        row.updated_at = now


def _locked_throttle_rows(
    db: Session,
    settings: Settings,
    *,
    factors: tuple[tuple[str, str, int], ...],
    now: datetime,
) -> list[tuple[AuthThrottle, int]]:
    keys = sorted((_throttle_key(settings, scope, value), scope, limit) for scope, value, limit in factors)
    values = [
        {
            "key_hash": key,
            "scope": scope,
            "failure_count": 0,
            "window_started_at": now,
            "locked_until": None,
            "updated_at": now,
        }
        for key, scope, _limit in keys
    ]
    dialect = db.bind.dialect.name if db.bind is not None else ""
    if dialect == "postgresql":
        db.execute(postgresql_insert(AuthThrottle).values(values).on_conflict_do_nothing())
    elif dialect == "sqlite":
        db.execute(sqlite_insert(AuthThrottle).values(values).on_conflict_do_nothing())
    else:
        for value in values:
            if db.get(AuthThrottle, value["key_hash"]) is None:
                db.add(AuthThrottle(**value))
        db.flush()
    rows = list(
        db.scalars(
            select(AuthThrottle)
            .where(AuthThrottle.key_hash.in_([key for key, _scope, _limit in keys]))
            .order_by(AuthThrottle.key_hash)
            .with_for_update()
        )
    )
    if len(rows) != len(keys):
        raise RuntimeError("could not initialize login throttle state")
    limits = {key: limit for key, _scope, limit in keys}
    return [(row, limits[row.key_hash]) for row in rows]


def _throttle_key(settings: Settings, scope: str, value: str) -> str:
    return hmac.new(
        settings.secret_key.get_secret_value().encode("utf-8"),
        f"{scope}:{value}".encode(),
        hashlib.sha256,
    ).hexdigest()


def normalize_phone(value: str) -> str:
    normalized = _PHONE_SEPARATORS.sub("", value.strip())
    if not _PHONE_PATTERN.fullmatch(normalized):
        raise ValueError("手机号格式不正确")
    return normalized


def validate_password_strength(password: str) -> None:
    if len(password) < 10 or len(password) > 128:
        raise ValueError("密码长度必须为 10–128 个字符")
    categories = sum(
        bool(pattern.search(password))
        for pattern in (
            re.compile(r"[a-z]"),
            re.compile(r"[A-Z]"),
            re.compile(r"\d"),
            re.compile(r"[^A-Za-z0-9]"),
        )
    )
    if categories < 3:
        raise ValueError("密码必须包含大小写字母、数字或符号中的至少三类")


def hash_password(password: str) -> str:
    validate_password_strength(password)
    return _PASSWORD_HASHER.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    try:
        return _PASSWORD_HASHER.verify(encoded, password)
    except (InvalidHashError, VerifyMismatchError):
        return False


def consume_dummy_password_check(password: str) -> None:
    verify_password(password, _DUMMY_PASSWORD_HASH)


def password_needs_rehash(encoded: str) -> bool:
    try:
        return _PASSWORD_HASHER.check_needs_rehash(encoded)
    except InvalidHashError:
        return True


def random_token(length: int = 48) -> str:
    return secrets.token_urlsafe(length)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_access_token(user: User, session_id: str, settings: Settings) -> tuple[str, datetime]:
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=settings.access_token_minutes)
    payload: dict[str, Any] = {
        "iss": "beta-center",
        "aud": "beta-center-api",
        "sub": user.id,
        "sid": session_id,
        "gen": user.session_generation,
        "role": user.role.value,
        "jti": random_token(16),
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    encoded = jwt.encode(payload, settings.secret_key.get_secret_value(), algorithm="HS256")
    return encoded, expires_at


def decode_access_token(encoded: str, settings: Settings) -> AccessClaims:
    try:
        payload = jwt.decode(
            encoded,
            settings.secret_key.get_secret_value(),
            algorithms=["HS256"],
            issuer="beta-center",
            audience="beta-center-api",
            options={"require": ["exp", "iat", "nbf", "sub", "sid", "gen", "role", "jti"]},
        )
        expires_at = datetime.fromtimestamp(int(payload["exp"]), UTC)
        return AccessClaims(
            user_id=str(payload["sub"]),
            session_id=str(payload["sid"]),
            generation=int(payload["gen"]),
            role=UserRole(str(payload["role"])),
            expires_at=expires_at,
        )
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
        raise InvalidTokenError("无效或已过期的登录状态") from exc


def aware_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def is_expired(value: datetime, *, now: datetime | None = None) -> bool:
    return aware_utc(value) <= (now or datetime.now(UTC))
