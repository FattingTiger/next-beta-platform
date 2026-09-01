"""Add recoverable soft deletion for Bug feedback.

Revision ID: 9c4f7b21a6d2
Revises: 6dd058b7b400
Create Date: 2026-08-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "9c4f7b21a6d2"
down_revision: str | None = "6dd058b7b400"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("bugs", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_bugs_deleted_at", "bugs", ["deleted_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_bugs_deleted_at", table_name="bugs")
    op.drop_column("bugs", "deleted_at")
