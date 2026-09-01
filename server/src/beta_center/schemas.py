from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from beta_center.models import (
    AppStatus,
    BugResolution,
    BugStatus,
    BugVisibility,
    DownloadStatus,
    UserRole,
    VersionStatus,
)
from beta_center.security import normalize_phone, validate_password_strength

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)]
PackageName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)+$"),
]


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class ErrorDetail(ApiModel):
    code: str
    message: str
    request_id: str | None = None


class ErrorResponse(ApiModel):
    error: ErrorDetail


class Page[T](ApiModel):
    items: list[T]
    total: int
    page: int
    page_size: int


class LoginRequest(ApiModel):
    phone: str
    password: str = Field(min_length=1, max_length=128)
    client_name: str = Field(default="android", max_length=80)

    @field_validator("phone")
    @classmethod
    def normalize_phone_value(cls, value: str) -> str:
        return normalize_phone(value)


class RefreshRequest(ApiModel):
    refresh_token: str | None = Field(default=None, min_length=20, max_length=500)


class ChangePasswordRequest(ApiModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        validate_password_strength(value)
        return value


class ReauthenticateRequest(ApiModel):
    password: str = Field(min_length=1, max_length=128)


class PermanentDeleteRequest(ApiModel):
    current_password: str = Field(min_length=1, max_length=128)


class UserSummary(ApiModel):
    id: str
    display_name: str
    phone: str
    role: UserRole
    is_active: bool
    must_change_password: bool
    group_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None


class AuthResponse(ApiModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_at: datetime
    csrf_token: str
    user: UserSummary


class UserCreate(ApiModel):
    display_name: Name
    phone: str
    initial_password: str = Field(min_length=10, max_length=128)
    role: UserRole = UserRole.TESTER
    group_ids: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("phone")
    @classmethod
    def normalize_phone_value(cls, value: str) -> str:
        return normalize_phone(value)

    @field_validator("initial_password")
    @classmethod
    def validate_initial_password(cls, value: str) -> str:
        validate_password_strength(value)
        return value

    @field_validator("group_ids")
    @classmethod
    def unique_groups(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))


class UserUpdate(ApiModel):
    display_name: Name | None = None
    phone: str | None = None
    role: UserRole | None = None
    is_active: bool | None = None
    group_ids: list[str] | None = Field(default=None, max_length=50)

    @field_validator("phone")
    @classmethod
    def normalize_phone_value(cls, value: str | None) -> str | None:
        return normalize_phone(value) if value is not None else None

    @field_validator("group_ids")
    @classmethod
    def unique_groups(cls, value: list[str] | None) -> list[str] | None:
        return list(dict.fromkeys(value)) if value is not None else None


class PasswordReset(ApiModel):
    new_password: str = Field(min_length=10, max_length=128)
    force_change: Literal[True] = True

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        validate_password_strength(value)
        return value


class GroupCreate(ApiModel):
    name: Name
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] = ""
    member_ids: list[str] = Field(default_factory=list, max_length=200)
    app_ids: list[str] = Field(default_factory=list, max_length=200)

    @field_validator("member_ids", "app_ids")
    @classmethod
    def unique_ids(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))


class GroupUpdate(ApiModel):
    name: Name | None = None
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None
    is_active: bool | None = None
    member_ids: list[str] | None = Field(default=None, max_length=200)
    app_ids: list[str] | None = Field(default=None, max_length=200)

    @field_validator("member_ids", "app_ids")
    @classmethod
    def unique_ids(cls, value: list[str] | None) -> list[str] | None:
        return list(dict.fromkeys(value)) if value is not None else None


class GroupSummary(ApiModel):
    id: str
    name: str
    description: str
    is_active: bool
    member_ids: list[str] = Field(default_factory=list)
    app_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class AppCreate(ApiModel):
    name: Name
    package_name: PackageName
    short_description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=180)] = ""
    description: Description = ""
    group_ids: list[str] = Field(default_factory=list, max_length=200)

    @field_validator("group_ids")
    @classmethod
    def unique_groups(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))


class AppUpdate(ApiModel):
    name: Name | None = None
    short_description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=180)] | None = None
    description: Description | None = None
    status: AppStatus | None = None
    group_ids: list[str] | None = Field(default=None, max_length=200)

    @field_validator("group_ids")
    @classmethod
    def unique_groups(cls, value: list[str] | None) -> list[str] | None:
        return list(dict.fromkeys(value)) if value is not None else None


class VersionSummary(ApiModel):
    id: str
    version_name: str
    version_code: int
    min_sdk: int | None
    target_sdk: int | None
    file_size: int
    sha256: str
    signing_cert_sha256: str
    release_notes: str
    status: VersionStatus
    download_enabled: bool
    created_at: datetime
    published_at: datetime | None


class ScreenshotSummary(ApiModel):
    id: str
    position: int
    content_type: str
    url: str


class AppSummary(ApiModel):
    id: str
    name: str
    package_name: str
    short_description: str
    status: AppStatus
    icon_url: str | None
    current_version: VersionSummary | None
    group_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class AppDetail(AppSummary):
    description: str
    screenshots: list[ScreenshotSummary] = Field(default_factory=list)
    versions: list[VersionSummary] = Field(default_factory=list)


class VersionPublishRequest(ApiModel):
    release_notes: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]


class BugCreate(ApiModel):
    app_id: str
    version_id: str
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)]
    description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=10_000)]
    reproduction_steps: Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)] = ""
    device_model: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] = ""
    android_version: Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)] = ""
    client_version: Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)] = ""
    visibility: BugVisibility = BugVisibility.GROUP


class BugTextUpdate(ApiModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)] | None = (
        None
    )
    description: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=10_000)] | None
    ) = None
    reproduction_steps: Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)] | None = (
        None
    )

    @model_validator(mode="after")
    def validate_changes(self) -> BugTextUpdate:
        changes = self.model_dump(exclude_unset=True)
        if not changes:
            raise ValueError("至少需要修改一个 Bug 文本字段")
        if any(value is None for value in changes.values()):
            raise ValueError("Bug 文本字段不能为 null")
        return self


class BugCommentCreate(ApiModel):
    content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]


class AdminBugCommentCreate(BugCommentCreate):
    internal: bool = False


class BugStatusUpdate(ApiModel):
    status: BugStatus
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)] = ""
    resolution: BugResolution | None = None
    fix_version_id: str | None = None

    @model_validator(mode="after")
    def validate_close_fields(self) -> BugStatusUpdate:
        if self.status == BugStatus.CLOSED and self.resolution is None:
            raise ValueError("关闭 Bug 时必须选择处理结论")
        if self.status == BugStatus.VERIFYING and not self.fix_version_id:
            raise ValueError("待验证状态必须关联修复版本")
        if self.resolution == BugResolution.FIXED and not self.fix_version_id:
            raise ValueError("处理结论为已修复时必须关联修复版本")
        if self.status != BugStatus.CLOSED and self.resolution is not None:
            raise ValueError("只有关闭 Bug 时可以填写处理结论")
        return self


class BugVerificationRequest(ApiModel):
    accepted: bool
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)] = ""


class BugVisibilityUpdate(ApiModel):
    visibility: BugVisibility


class BugDeletionUpdate(ApiModel):
    deleted: bool


class BugAttachmentSummary(ApiModel):
    id: str
    content_type: str
    file_size: int
    url: str


class BugCommentSummary(ApiModel):
    id: str
    author_id: str
    author_name: str
    content: str
    is_admin_note: bool
    created_at: datetime


class BugTransitionSummary(ApiModel):
    id: str
    actor_id: str
    actor_name: str
    from_status: BugStatus | None
    to_status: BugStatus
    note: str
    created_at: datetime


class BugSummary(ApiModel):
    id: str
    reference: str
    app_id: str
    app_name: str
    version_id: str
    version_name: str
    # Group-visible bugs deliberately omit reporter identity for peers.  The
    # fields stay present in the typed model so reporter/admin responses retain
    # their richer contract; user routes exclude them when their value is None.
    reporter_id: str | None
    reporter_name: str | None
    title: str
    description: str | None
    reproduction_steps: str | None
    device_model: str | None
    android_version: str | None
    client_version: str | None
    status: BugStatus
    visibility: BugVisibility
    resolution: BugResolution | None
    resolution_note: str
    fix_version_id: str | None
    attachments: list[BugAttachmentSummary] = Field(default_factory=list)
    comments: list[BugCommentSummary] = Field(default_factory=list)
    transitions: list[BugTransitionSummary] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None
    deleted_at: datetime | None


class DownloadStartRequest(ApiModel):
    version_id: str
    client_request_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$",
    )
    device_model: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] = ""
    android_version: Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)] = ""
    client_version: Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)] = ""


class DownloadTicket(ApiModel):
    download_id: str
    client_request_id: str
    ticket: str
    url: str
    expires_at: datetime
    file_size: int
    sha256: str
    filename: str


class DownloadCompleteRequest(ApiModel):
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bytes_received: int = Field(ge=1)


class DownloadFailureRequest(ApiModel):
    status: DownloadStatus
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]

    @field_validator("status")
    @classmethod
    def validate_failure_status(cls, value: DownloadStatus) -> DownloadStatus:
        if value not in {DownloadStatus.FAILED, DownloadStatus.CANCELLED}:
            raise ValueError("状态必须是 failed 或 cancelled")
        return value


class DownloadSummary(ApiModel):
    id: str
    user_id: str
    app_id: str
    version_id: str
    status: DownloadStatus
    bytes_sent: int
    device_model: str
    android_version: str
    client_version: str
    request_ip: str
    failure_reason: str
    created_at: datetime
    completed_at: datetime | None


class DashboardSummary(ApiModel):
    active_users: int
    active_apps: int
    published_versions: int
    open_bugs: int
    downloads_started_7d: int
    downloads_completed_7d: int


class AuditSummary(ApiModel):
    id: str
    actor_id: str | None
    actor_name: str | None
    action: str
    entity_type: str
    entity_id: str | None
    outcome: str
    reason_code: str
    request_id: str
    details: dict[str, object]
    request_ip: str
    created_at: datetime


def bug_reference(bug_id: str) -> str:
    compact = re.sub(r"[^0-9a-f]", "", bug_id.lower())
    return f"BT-{compact[:8].upper()}"
