"""ISSUE-078: persisted per-user profile + notification prefs (user_profiles).

Adds the ``user_profiles`` table that stores a user's display name and
notification toggles server-side (replacing the old localStorage-only state), so
preferences follow the user across devices and can drive notification delivery.

On a fresh database the baseline revision's ``create_all`` already builds the
table at its current shape, so the create is guarded to be idempotent — it only
acts on a database migrated to head before this revision existed.

Revision ID: 2b3c4d5e6f70
Revises: 1a2b3c4d5e6f
Create Date: 2026-06-15 00:30:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "2b3c4d5e6f70"
down_revision: Union[str, Sequence[str], None] = "1a2b3c4d5e6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if "user_profiles" in insp.get_table_names():
        return
    op.create_table(
        "user_profiles",
        sa.Column("user_id", sa.String(length=255), primary_key=True),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("email_alerts", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("low_stock_alerts", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("daily_summary", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("transaction_alerts", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_user_profiles_user_id", "user_profiles", ["user_id"])


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if "user_profiles" not in insp.get_table_names():
        return
    op.drop_table("user_profiles")
