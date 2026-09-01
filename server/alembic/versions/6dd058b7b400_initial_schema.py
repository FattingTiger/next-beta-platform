"""Create the initial beta-center schema.

Revision ID: 6dd058b7b400
Revises:
Create Date: 2026-08-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "6dd058b7b400"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _user_role() -> sa.Enum:
    return sa.Enum("ADMIN", "TESTER", name="userrole", native_enum=False)


def _app_status() -> sa.Enum:
    return sa.Enum("DRAFT", "PUBLISHED", "ARCHIVED", name="appstatus", native_enum=False)


def _version_status() -> sa.Enum:
    return sa.Enum("DRAFT", "PUBLISHED", "DISABLED", name="versionstatus", native_enum=False)


def _bug_status() -> sa.Enum:
    return sa.Enum("PENDING", "IN_PROGRESS", "VERIFYING", "CLOSED", name="bugstatus", native_enum=False)


def _bug_visibility() -> sa.Enum:
    return sa.Enum("GROUP", "PRIVATE", name="bugvisibility", native_enum=False)


def _bug_resolution() -> sa.Enum:
    return sa.Enum(
        "FIXED",
        "DUPLICATE",
        "NOT_A_BUG",
        "CANNOT_REPRODUCE",
        "WONT_FIX",
        name="bugresolution",
        native_enum=False,
    )


def _download_status() -> sa.Enum:
    return sa.Enum(
        "STARTED",
        "COMPLETED",
        "FAILED",
        "CANCELLED",
        name="downloadstatus",
        native_enum=False,
    )


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("display_name", sa.String(length=80), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", _user_role(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("must_change_password", sa.Boolean(), nullable=False),
        sa.Column("failed_login_count", sa.Integer(), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("session_generation", sa.Integer(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_phone", "users", ["phone"], unique=True)

    op.create_table(
        "test_groups",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    # The FK for current_version_id is added after app_versions exists. This
    # makes the cyclic apps/app_versions relationship portable across engines.
    op.create_table(
        "apps",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("package_name", sa.String(length=255), nullable=False),
        sa.Column("short_description", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", _app_status(), nullable=False),
        sa.Column("icon_storage_key", sa.String(length=255), nullable=True),
        sa.Column("signing_cert_sha256", sa.String(length=64), nullable=True),
        sa.Column("current_version_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_apps_current_version_id", "apps", ["current_version_id"], unique=False)
    op.create_index("ix_apps_package_name", "apps", ["package_name"], unique=True)

    op.create_table(
        "app_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("app_id", sa.String(length=36), nullable=False),
        sa.Column("version_name", sa.String(length=100), nullable=False),
        sa.Column("version_code", sa.Integer(), nullable=False),
        sa.Column("min_sdk", sa.Integer(), nullable=True),
        sa.Column("target_sdk", sa.Integer(), nullable=True),
        sa.Column("file_storage_key", sa.String(length=255), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("signing_cert_sha256", sa.String(length=64), nullable=False),
        sa.Column("release_notes", sa.Text(), nullable=False),
        sa.Column("status", _version_status(), nullable=False),
        sa.Column("download_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_by_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["app_id"],
            ["apps.id"],
            name="fk_app_versions_app_id_apps",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name="fk_app_versions_created_by_id_users",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("app_id", "id", name="uq_app_version_app_id_id"),
        sa.UniqueConstraint("app_id", "sha256", name="uq_app_version_sha256"),
        sa.UniqueConstraint("app_id", "version_code", name="uq_app_version_code"),
        sa.UniqueConstraint("file_storage_key"),
    )
    op.create_index("ix_app_versions_app_id", "app_versions", ["app_id"], unique=False)
    op.create_index(
        "uq_app_one_download_enabled_version",
        "app_versions",
        ["app_id"],
        unique=True,
        postgresql_where=sa.text("download_enabled"),
        sqlite_where=sa.text("download_enabled = 1"),
    )
    with op.batch_alter_table("apps") as batch_op:
        batch_op.create_foreign_key(
            "fk_apps_current_version_same_app",
            "app_versions",
            ["id", "current_version_id"],
            ["app_id", "id"],
        )

    op.create_table(
        "app_group_visibility",
        sa.Column("app_id", sa.String(length=36), nullable=False),
        sa.Column("group_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["app_id"],
            ["apps.id"],
            name="fk_app_group_visibility_app_id_apps",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["test_groups.id"],
            name="fk_app_group_visibility_group_id_test_groups",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("app_id", "group_id"),
    )
    op.create_table(
        "user_group_members",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("group_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_group_members_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["test_groups.id"],
            name="fk_user_group_members_group_id_test_groups",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "group_id"),
    )

    op.create_table(
        "app_screenshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("app_id", sa.String(length=36), nullable=False),
        sa.Column("storage_key", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=50), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["app_id"],
            ["apps.id"],
            name="fk_app_screenshots_app_id_apps",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("app_id", "position", name="uq_app_screenshot_position"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index("ix_app_screenshots_app_id", "app_screenshots", ["app_id"], unique=False)

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("actor_id", sa.String(length=36), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=60), nullable=False),
        sa.Column("entity_id", sa.String(length=80), nullable=True),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("reason_code", sa.String(length=80), nullable=False),
        sa.Column("request_id", sa.String(length=80), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("request_ip", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name="fk_audit_logs_actor_id_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_created_action", "audit_logs", ["created_at", "action"], unique=False)

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("refresh_token_hash", sa.String(length=64), nullable=False),
        sa.Column("csrf_token_hash", sa.String(length=64), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("user_agent", sa.String(length=300), nullable=False),
        sa.Column("request_ip", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reauthenticated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_auth_sessions_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("refresh_token_hash"),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"], unique=False)

    op.create_table(
        "auth_throttles",
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key_hash"),
    )

    op.create_table(
        "bugs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("app_id", sa.String(length=36), nullable=False),
        sa.Column("version_id", sa.String(length=36), nullable=False),
        sa.Column("reporter_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("reproduction_steps", sa.Text(), nullable=False),
        sa.Column("device_model", sa.String(length=120), nullable=False),
        sa.Column("android_version", sa.String(length=50), nullable=False),
        sa.Column("client_version", sa.String(length=50), nullable=False),
        sa.Column("status", _bug_status(), nullable=False),
        sa.Column("visibility", _bug_visibility(), nullable=False),
        sa.Column("resolution", _bug_resolution(), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=False),
        sa.Column("fix_version_id", sa.String(length=36), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["app_id"], ["apps.id"], name="fk_bugs_app_id_apps"),
        sa.ForeignKeyConstraint(
            ["app_id", "version_id"],
            ["app_versions.app_id", "app_versions.id"],
            name="fk_bug_version_same_app",
        ),
        sa.ForeignKeyConstraint(
            ["app_id", "fix_version_id"],
            ["app_versions.app_id", "app_versions.id"],
            name="fk_bug_fix_version_same_app",
        ),
        sa.ForeignKeyConstraint(["reporter_id"], ["users.id"], name="fk_bugs_reporter_id_users"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bug_app_status_updated", "bugs", ["app_id", "status", "updated_at"])
    op.create_index("ix_bug_reporter_updated", "bugs", ["reporter_id", "updated_at"])

    op.create_table(
        "download_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("app_id", sa.String(length=36), nullable=False),
        sa.Column("version_id", sa.String(length=36), nullable=False),
        sa.Column("client_request_id", sa.String(length=36), nullable=False),
        sa.Column("status", _download_status(), nullable=False),
        sa.Column("ticket_hash", sa.String(length=64), nullable=False),
        sa.Column("ticket_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bytes_sent", sa.Integer(), nullable=False),
        sa.Column("device_model", sa.String(length=120), nullable=False),
        sa.Column("android_version", sa.String(length=50), nullable=False),
        sa.Column("client_version", sa.String(length=50), nullable=False),
        sa.Column("request_ip", sa.String(length=64), nullable=False),
        sa.Column("user_agent", sa.String(length=300), nullable=False),
        sa.Column("failure_reason", sa.String(length=300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_download_records_user_id_users"),
        sa.ForeignKeyConstraint(["app_id"], ["apps.id"], name="fk_download_records_app_id_apps"),
        sa.ForeignKeyConstraint(
            ["app_id", "version_id"],
            ["app_versions.app_id", "app_versions.id"],
            name="fk_download_version_same_app",
        ),
        sa.CheckConstraint("bytes_sent >= 0", name="ck_download_bytes_nonnegative"),
        sa.CheckConstraint(
            "status != 'COMPLETED' OR (completed_at IS NOT NULL AND bytes_sent > 0)",
            name="ck_download_completed_evidence",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticket_hash"),
        sa.UniqueConstraint("user_id", "client_request_id", name="uq_download_user_client_request"),
    )
    op.create_index("ix_download_user_created", "download_records", ["user_id", "created_at"])
    op.create_index("ix_download_version_status", "download_records", ["version_id", "status"])

    op.create_table(
        "bug_attachments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("bug_id", sa.String(length=36), nullable=False),
        sa.Column("storage_key", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=50), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["bug_id"],
            ["bugs.id"],
            name="fk_bug_attachments_bug_id_bugs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index("ix_bug_attachments_bug_id", "bug_attachments", ["bug_id"])

    op.create_table(
        "bug_comments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("bug_id", sa.String(length=36), nullable=False),
        sa.Column("author_id", sa.String(length=36), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("is_admin_note", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["bug_id"],
            ["bugs.id"],
            name="fk_bug_comments_bug_id_bugs",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
            name="fk_bug_comments_author_id_users",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bug_comments_bug_id", "bug_comments", ["bug_id"])

    op.create_table(
        "bug_transitions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("bug_id", sa.String(length=36), nullable=False),
        sa.Column("actor_id", sa.String(length=36), nullable=False),
        sa.Column("from_status", _bug_status(), nullable=True),
        sa.Column("to_status", _bug_status(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["bug_id"],
            ["bugs.id"],
            name="fk_bug_transitions_bug_id_bugs",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name="fk_bug_transitions_actor_id_users",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bug_transitions_bug_id", "bug_transitions", ["bug_id"])


def downgrade() -> None:
    op.drop_index("ix_bug_transitions_bug_id", table_name="bug_transitions")
    op.drop_table("bug_transitions")
    op.drop_index("ix_bug_comments_bug_id", table_name="bug_comments")
    op.drop_table("bug_comments")
    op.drop_index("ix_bug_attachments_bug_id", table_name="bug_attachments")
    op.drop_table("bug_attachments")
    op.drop_index("ix_download_version_status", table_name="download_records")
    op.drop_index("ix_download_user_created", table_name="download_records")
    op.drop_table("download_records")
    op.drop_index("ix_bug_reporter_updated", table_name="bugs")
    op.drop_index("ix_bug_app_status_updated", table_name="bugs")
    op.drop_table("bugs")
    op.drop_table("auth_throttles")
    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_index("ix_audit_created_action", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index("ix_app_screenshots_app_id", table_name="app_screenshots")
    op.drop_table("app_screenshots")
    op.drop_table("user_group_members")
    op.drop_table("app_group_visibility")

    with op.batch_alter_table("apps") as batch_op:
        batch_op.drop_constraint("fk_apps_current_version_same_app", type_="foreignkey")
    op.drop_index("uq_app_one_download_enabled_version", table_name="app_versions")
    op.drop_index("ix_app_versions_app_id", table_name="app_versions")
    op.drop_table("app_versions")
    op.drop_index("ix_apps_package_name", table_name="apps")
    op.drop_index("ix_apps_current_version_id", table_name="apps")
    op.drop_table("apps")
    op.drop_table("test_groups")
    op.drop_index("ix_users_phone", table_name="users")
    op.drop_table("users")
