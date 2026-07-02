"""ISSUE-225 (M10 Admin): admin console — add the ``platform_settings`` table.

Backs the operator admin console's platform-global key/value store, the first
user being maintenance mode (``{enabled, message}`` under key ``maintenance_mode``).
Unlike tenant-owned ``store_settings``, these rows belong to the platform itself,
so a single row per ``key`` is the whole platform's value (no tenancy column).

On a fresh database the baseline revision's ``create_all`` already builds this
table at its current shape, so the create is guarded to be idempotent — it only
acts on a database that was migrated to head before this revision existed.

Revision ID: 225adm0a1b2c
Revises: 224scn0a1b2c
Create Date: 2026-07-01 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "225adm0a1b2c"
down_revision: Union[str, Sequence[str], None] = "224scn0a1b2c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if "platform_settings" not in insp.get_table_names():
        op.create_table(
            "platform_settings",
            sa.Column("key", sa.String(), primary_key=True, nullable=False),
            sa.Column("value", sa.Text(), nullable=True),
            sa.Column("updated_by", sa.String(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_platform_settings_key", "platform_settings", ["key"])


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if "platform_settings" in insp.get_table_names():
        op.drop_table("platform_settings")
