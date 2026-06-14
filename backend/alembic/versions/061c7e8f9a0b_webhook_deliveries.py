"""ISSUE-029: webhook delivery log table.

Adds ``webhook_deliveries`` — the append-only log of webhook dispatch outcomes
behind the WebhookManagement "Delivery Logs" tab and its "Deliveries Today"
stat (which previously consumed a non-existent route, swallowing the 404).

On a fresh database the baseline ``create_all`` already builds the table at its
current shape, so the create is guarded to be idempotent — it only backfills a
database migrated to head before this revision existed.

Revision ID: 061c7e8f9a0b
Revises: 060b5c6d7e8f
Create Date: 2026-06-14 11:05:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "061c7e8f9a0b"
down_revision: Union[str, Sequence[str], None] = "060b5c6d7e8f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "webhook_deliveries"


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if _TABLE in insp.get_table_names():
        # Fresh DB: create_all already built the table at the current shape.
        return
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("webhook_id", sa.Integer(), nullable=True),
        sa.Column("event", sa.String(), nullable=False),
        sa.Column("target_url", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("response_time_ms", sa.Integer(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(f"ix_{_TABLE}_user_id", _TABLE, ["user_id"])
    op.create_index(f"ix_{_TABLE}_created_at", _TABLE, ["created_at"])
    op.create_index(f"ix_{_TABLE}_id", _TABLE, ["id"])


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if _TABLE not in insp.get_table_names():
        return
    op.drop_table(_TABLE)
