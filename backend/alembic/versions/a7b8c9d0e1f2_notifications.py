"""F-052 / UX-08: persisted notification center.

Adds the ``notifications`` table that backs the notification center. The page used
to synthesize its feed per-request with a no-op ``mark-read`` (read state was a lie
across reloads); this table persists the feed and its read state so a "mark as
read" survives a refetch, and system alerts (low-stock / ZATCA-failed /
subscription) are materialized idempotently by ``dedupe_key``.

On a fresh database the baseline revision's ``create_all`` already builds this table
at its current shape, so the create is guarded to be idempotent — it only acts on a
database that was migrated to head before this revision existed. See finding F-052.

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-06-03 20:30:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if "notifications" not in insp.get_table_names():
        op.create_table(
            "notifications",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("client_id", sa.Integer(), nullable=True),
            sa.Column("type", sa.String(), nullable=False, server_default="system"),
            sa.Column("title", sa.String(), nullable=True),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("dedupe_key", sa.String(), nullable=True),
            sa.Column("is_read", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
        op.create_index("ix_notifications_client_id", "notifications", ["client_id"])
        op.create_index("ix_notifications_dedupe_key", "notifications", ["dedupe_key"])


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if "notifications" in insp.get_table_names():
        op.drop_index("ix_notifications_dedupe_key", table_name="notifications")
        op.drop_index("ix_notifications_client_id", table_name="notifications")
        op.drop_index("ix_notifications_user_id", table_name="notifications")
        op.drop_table("notifications")
