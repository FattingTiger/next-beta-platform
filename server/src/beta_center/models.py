from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, ClassVar

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def new_id() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[object, object]] = {dict[str, Any]: JSON}


class UserRole(StrEnum):
    ADMIN = "admin"
    TESTER = "tester"


class AppStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class VersionStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    DISABLED = "disabled"


class BugStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    VERIFYING = "verifying"
    CLOSED = "closed"


class BugVisibility(StrEnum):
    GROUP = "group"
    PRIVATE = "private"


class BugResolution(StrEnum):
    FIXED = "fixed"
    DUPLICATE = "duplicate"
    NOT_A_BUG = "not_a_bug"
    CANNOT_REPRODUCE = "cannot_reproduce"
    WONT_FIX = "wont_fix"


class DownloadStatus(StrEnum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


user_group_members = Table(
    "user_group_members",
    Base.metadata,
    Column("user_id", String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("group_id", String(36), ForeignKey("test_groups.id", ondelete="CASCADE"), primary_key=True),
)


app_group_visibility = Table(
    "app_group_visibility",
    Base.metadata,
    Column("app_id", String(36), ForeignKey("apps.id", ondelete="CASCADE"), primary_key=True),
    Column("group_id", String(36), ForeignKey("test_groups.id", ondelete="CASCADE"), primary_key=True),
)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, native_enum=False), default=UserRole.TESTER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    session_generation: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    groups: Mapped[list[TestGroup]] = relationship(
        secondary=user_group_members,
        back_populates="members",
        lazy="selectin",
    )
    sessions: Mapped[list[AuthSession]] = relationship(back_populates="user", cascade="all, delete-orphan")


class TestGroup(TimestampMixin, Base):
    __tablename__ = "test_groups"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    members: Mapped[list[User]] = relationship(
        secondary=user_group_members,
        back_populates="groups",
        lazy="selectin",
    )
    apps: Mapped[list[App]] = relationship(
        secondary=app_group_visibility,
        back_populates="visible_groups",
        lazy="selectin",
    )


class App(TimestampMixin, Base):
    __tablename__ = "apps"
    __table_args__ = (
        ForeignKeyConstraint(
            ["id", "current_version_id"],
            ["app_versions.app_id", "app_versions.id"],
            name="fk_apps_current_version_same_app",
            use_alter=True,
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    package_name: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    short_description: Mapped[str] = mapped_column(String(180), default="", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[AppStatus] = mapped_column(Enum(AppStatus, native_enum=False), default=AppStatus.DRAFT)
    icon_storage_key: Mapped[str | None] = mapped_column(String(255))
    signing_cert_sha256: Mapped[str | None] = mapped_column(String(64))
    current_version_id: Mapped[str | None] = mapped_column(String(36), index=True)

    visible_groups: Mapped[list[TestGroup]] = relationship(
        secondary=app_group_visibility,
        back_populates="apps",
        lazy="selectin",
    )
    versions: Mapped[list[AppVersion]] = relationship(
        back_populates="app",
        cascade="all, delete-orphan",
        foreign_keys="AppVersion.app_id",
        order_by="AppVersion.version_code.desc()",
    )
    screenshots: Mapped[list[AppScreenshot]] = relationship(
        back_populates="app", cascade="all, delete-orphan", order_by="AppScreenshot.position"
    )


class AppVersion(Base):
    __tablename__ = "app_versions"
    __table_args__ = (
        UniqueConstraint("app_id", "id", name="uq_app_version_app_id_id"),
        UniqueConstraint("app_id", "version_code", name="uq_app_version_code"),
        UniqueConstraint("app_id", "sha256", name="uq_app_version_sha256"),
        Index(
            "uq_app_one_download_enabled_version",
            "app_id",
            unique=True,
            postgresql_where=text("download_enabled"),
            sqlite_where=text("download_enabled = 1"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    app_id: Mapped[str] = mapped_column(String(36), ForeignKey("apps.id", ondelete="CASCADE"), index=True)
    version_name: Mapped[str] = mapped_column(String(100), nullable=False)
    version_code: Mapped[int] = mapped_column(Integer, nullable=False)
    min_sdk: Mapped[int | None] = mapped_column(Integer)
    target_sdk: Mapped[int | None] = mapped_column(Integer)
    file_storage_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    signing_cert_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    release_notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[VersionStatus] = mapped_column(
        Enum(VersionStatus, native_enum=False), default=VersionStatus.DRAFT, nullable=False
    )
    download_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    app: Mapped[App] = relationship(back_populates="versions", foreign_keys=[app_id])
    created_by: Mapped[User] = relationship(foreign_keys=[created_by_id])


class AppScreenshot(Base):
    __tablename__ = "app_screenshots"
    __table_args__ = (UniqueConstraint("app_id", "position", name="uq_app_screenshot_position"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    app_id: Mapped[str] = mapped_column(String(36), ForeignKey("apps.id", ondelete="CASCADE"), index=True)
    storage_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    content_type: Mapped[str] = mapped_column(String(50), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    app: Mapped[App] = relationship(back_populates="screenshots")


class Bug(TimestampMixin, Base):
    __tablename__ = "bugs"
    __table_args__ = (
        Index("ix_bug_app_status_updated", "app_id", "status", "updated_at"),
        Index("ix_bug_reporter_updated", "reporter_id", "updated_at"),
        ForeignKeyConstraint(
            ["app_id", "version_id"],
            ["app_versions.app_id", "app_versions.id"],
            name="fk_bug_version_same_app",
        ),
        ForeignKeyConstraint(
            ["app_id", "fix_version_id"],
            ["app_versions.app_id", "app_versions.id"],
            name="fk_bug_fix_version_same_app",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    app_id: Mapped[str] = mapped_column(String(36), ForeignKey("apps.id"), nullable=False)
    version_id: Mapped[str] = mapped_column(String(36), nullable=False)
    reporter_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    reproduction_steps: Mapped[str] = mapped_column(Text, default="", nullable=False)
    device_model: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    android_version: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    client_version: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    status: Mapped[BugStatus] = mapped_column(Enum(BugStatus, native_enum=False), default=BugStatus.PENDING)
    visibility: Mapped[BugVisibility] = mapped_column(
        Enum(BugVisibility, native_enum=False), default=BugVisibility.GROUP
    )
    resolution: Mapped[BugResolution | None] = mapped_column(Enum(BugResolution, native_enum=False))
    resolution_note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    fix_version_id: Mapped[str | None] = mapped_column(String(36))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    app: Mapped[App] = relationship(foreign_keys=[app_id])
    version: Mapped[AppVersion] = relationship(foreign_keys=[version_id])
    fix_version: Mapped[AppVersion | None] = relationship(foreign_keys=[fix_version_id])
    reporter: Mapped[User] = relationship(foreign_keys=[reporter_id])
    attachments: Mapped[list[BugAttachment]] = relationship(
        back_populates="bug", cascade="all, delete-orphan", order_by="BugAttachment.created_at"
    )
    comments: Mapped[list[BugComment]] = relationship(
        back_populates="bug", cascade="all, delete-orphan", order_by="BugComment.created_at"
    )
    transitions: Mapped[list[BugTransition]] = relationship(
        back_populates="bug", cascade="all, delete-orphan", order_by="BugTransition.created_at"
    )


class BugAttachment(Base):
    __tablename__ = "bug_attachments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    bug_id: Mapped[str] = mapped_column(String(36), ForeignKey("bugs.id", ondelete="CASCADE"), index=True)
    storage_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    content_type: Mapped[str] = mapped_column(String(50), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    bug: Mapped[Bug] = relationship(back_populates="attachments")


class BugComment(Base):
    __tablename__ = "bug_comments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    bug_id: Mapped[str] = mapped_column(String(36), ForeignKey("bugs.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_admin_note: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    bug: Mapped[Bug] = relationship(back_populates="comments")
    author: Mapped[User] = relationship()


class BugTransition(Base):
    __tablename__ = "bug_transitions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    bug_id: Mapped[str] = mapped_column(String(36), ForeignKey("bugs.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    from_status: Mapped[BugStatus | None] = mapped_column(Enum(BugStatus, native_enum=False))
    to_status: Mapped[BugStatus] = mapped_column(Enum(BugStatus, native_enum=False), nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    bug: Mapped[Bug] = relationship(back_populates="transitions")
    actor: Mapped[User] = relationship()


class DownloadRecord(Base):
    __tablename__ = "download_records"
    __table_args__ = (
        Index("ix_download_user_created", "user_id", "created_at"),
        Index("ix_download_version_status", "version_id", "status"),
        UniqueConstraint("user_id", "client_request_id", name="uq_download_user_client_request"),
        ForeignKeyConstraint(
            ["app_id", "version_id"],
            ["app_versions.app_id", "app_versions.id"],
            name="fk_download_version_same_app",
        ),
        CheckConstraint("bytes_sent >= 0", name="ck_download_bytes_nonnegative"),
        CheckConstraint(
            "status != 'COMPLETED' OR (completed_at IS NOT NULL AND bytes_sent > 0)",
            name="ck_download_completed_evidence",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    app_id: Mapped[str] = mapped_column(String(36), ForeignKey("apps.id"), nullable=False)
    version_id: Mapped[str] = mapped_column(String(36), nullable=False)
    client_request_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[DownloadStatus] = mapped_column(
        Enum(DownloadStatus, native_enum=False), default=DownloadStatus.STARTED
    )
    ticket_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    ticket_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    bytes_sent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    device_model: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    android_version: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    client_version: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    request_ip: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    user_agent: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    failure_reason: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship()
    app: Mapped[App] = relationship(overlaps="version")
    version: Mapped[AppVersion] = relationship(overlaps="app")


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    refresh_token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    csrf_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    user_agent: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    request_ip: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    reauthenticated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="sessions")


class AuthThrottle(Base):
    __tablename__ = "auth_throttles"

    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_created_action", "created_at", "action"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(80))
    outcome: Mapped[str] = mapped_column(String(20), default="success", nullable=False)
    reason_code: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    request_id: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    request_ip: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    actor: Mapped[User | None] = relationship()
