from __future__ import annotations

from sqlalchemy.orm import Session

from beta_center.models import App, AppVersion, AuditLog, Bug, DownloadRecord, TestGroup, User
from beta_center.schemas import (
    AppDetail,
    AppSummary,
    AuditSummary,
    BugAttachmentSummary,
    BugCommentSummary,
    BugSummary,
    BugTransitionSummary,
    DownloadSummary,
    GroupSummary,
    ScreenshotSummary,
    UserSummary,
    VersionSummary,
    bug_reference,
)


def user_summary(user: User) -> UserSummary:
    return UserSummary(
        id=user.id,
        display_name=user.display_name,
        phone=user.phone,
        role=user.role,
        is_active=user.is_active,
        must_change_password=user.must_change_password,
        group_ids=[group.id for group in user.groups],
        created_at=user.created_at,
        updated_at=user.updated_at,
        last_login_at=user.last_login_at,
    )


def group_summary(group: TestGroup) -> GroupSummary:
    return GroupSummary(
        id=group.id,
        name=group.name,
        description=group.description,
        is_active=group.is_active,
        member_ids=[member.id for member in group.members],
        app_ids=[app.id for app in group.apps],
        created_at=group.created_at,
        updated_at=group.updated_at,
    )


def version_summary(version: AppVersion) -> VersionSummary:
    return VersionSummary.model_validate(version)


def app_summary(db: Session, app: App) -> AppSummary:
    current = db.get(AppVersion, app.current_version_id) if app.current_version_id else None
    return AppSummary(
        id=app.id,
        name=app.name,
        package_name=app.package_name,
        short_description=app.short_description,
        status=app.status,
        icon_url=f"/api/v1/files/apps/{app.id}/icon" if app.icon_storage_key else None,
        current_version=version_summary(current) if current else None,
        group_ids=[group.id for group in app.visible_groups],
        created_at=app.created_at,
        updated_at=app.updated_at,
    )


def app_detail(db: Session, app: App, *, include_history: bool = True) -> AppDetail:
    base = app_summary(db, app)
    return AppDetail(
        **base.model_dump(),
        description=app.description,
        screenshots=[
            ScreenshotSummary(
                id=item.id,
                position=item.position,
                content_type=item.content_type,
                url=f"/api/v1/files/apps/{app.id}/screenshots/{item.id}",
            )
            for item in app.screenshots
        ],
        versions=[version_summary(item) for item in app.versions] if include_history else [],
    )


def bug_summary(
    bug: Bug,
    *,
    include_attachments: bool = True,
    include_internal_notes: bool = False,
    include_reporter_identity: bool = True,
    include_sensitive_details: bool = True,
) -> BugSummary:
    return BugSummary(
        id=bug.id,
        reference=bug_reference(bug.id),
        app_id=bug.app_id,
        app_name=bug.app.name,
        version_id=bug.version_id,
        version_name=bug.version.version_name,
        reporter_id=bug.reporter_id if include_reporter_identity else None,
        reporter_name=bug.reporter.display_name if include_reporter_identity else None,
        title=bug.title,
        description=bug.description if include_sensitive_details else None,
        reproduction_steps=bug.reproduction_steps if include_sensitive_details else None,
        device_model=bug.device_model if include_sensitive_details else None,
        android_version=bug.android_version if include_sensitive_details else None,
        client_version=bug.client_version if include_sensitive_details else None,
        status=bug.status,
        visibility=bug.visibility,
        resolution=bug.resolution,
        resolution_note=bug.resolution_note,
        fix_version_id=bug.fix_version_id,
        attachments=[
            BugAttachmentSummary(
                id=item.id,
                content_type=item.content_type,
                file_size=item.file_size,
                url=f"/api/v1/files/bugs/{bug.id}/attachments/{item.id}",
            )
            for item in bug.attachments
        ]
        if include_attachments
        else [],
        comments=[
            BugCommentSummary(
                id=item.id,
                author_id=item.author_id,
                author_name=item.author.display_name,
                content=item.content,
                is_admin_note=item.is_admin_note,
                created_at=item.created_at,
            )
            for item in bug.comments
            if include_internal_notes or not item.is_admin_note
        ]
        if include_sensitive_details
        else [],
        transitions=[
            BugTransitionSummary(
                id=item.id,
                actor_id=item.actor_id,
                actor_name=item.actor.display_name,
                from_status=item.from_status,
                to_status=item.to_status,
                note=item.note,
                created_at=item.created_at,
            )
            for item in bug.transitions
        ]
        if include_sensitive_details
        else [],
        created_at=bug.created_at,
        updated_at=bug.updated_at,
        closed_at=bug.closed_at,
        deleted_at=bug.deleted_at,
    )


def download_summary(record: DownloadRecord) -> DownloadSummary:
    return DownloadSummary.model_validate(record)


def audit_summary(entry: AuditLog) -> AuditSummary:
    return AuditSummary(
        id=entry.id,
        actor_id=entry.actor_id,
        actor_name=entry.actor.display_name if entry.actor else None,
        action=entry.action,
        entity_type=entry.entity_type,
        entity_id=entry.entity_id,
        outcome=entry.outcome,
        reason_code=entry.reason_code,
        request_id=entry.request_id,
        details=entry.details,
        request_ip=entry.request_ip,
        created_at=entry.created_at,
    )
