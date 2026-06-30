"""M6·Restaurant / issue-222: happy-hour pricing windows.

Adds the ``happy_hours`` table — owner-scoped time-of-day price-reduction windows.
A line added to an open ticket inside an active window is discounted server-side
by ``discount_percent`` off the catalog price (F-045, M6).

On a fresh database the baseline revision's ``create_all`` already builds the
table at its current shape, so the create is guarded idempotently — it only acts
on a database migrated to head before this revision existed.

Revision ID: 222hph6d0e1f
Revises: 222wtr5c8d9e
Create Date: 2026-06-30 23:45:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "222hph6d0e1f"
down_revision: Union[str, Sequence[str], None] = "222wtr5c8d9e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if "happy_hours" in insp.get_table_names():
        # Fresh DB: create_all already built the table at its current shape.
        return
    op.create_table(
        "happy_hours",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("discount_percent", sa.Float(), nullable=False, server_default="0"),
        sa.Column("start_minute", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("end_minute", sa.Integer(), nullable=False, server_default="1439"),
        sa.Column("days_of_week", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_happy_hours_user_id", "happy_hours", ["user_id"])
    op.create_index("ix_happy_hours_client_id", "happy_hours", ["client_id"])


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if "happy_hours" in insp.get_table_names():
        op.drop_table("happy_hours")
