"""M5·CRM / issue-221: marketing campaigns.

Adds the ``campaigns`` table — named marketing sends on a channel (sms/email)
carrying a message, optionally targeting one customer group.

On a fresh database the baseline revision's ``create_all`` already builds the table
at its current shape, so the create is guarded idempotently — it only acts on a
database migrated to head before this revision existed.

Revision ID: c3d4e5f6a8b9
Revises: b2c3d4e5f6a8
Create Date: 2026-06-30 22:45:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a8b9"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if "campaigns" not in insp.get_table_names():
        op.create_table(
            "campaigns",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("client_id", sa.Integer(), nullable=True),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("channel", sa.String(), nullable=False, server_default="sms"),
            sa.Column("message", sa.String(), nullable=True),
            sa.Column("target_group_id", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(), nullable=False, server_default="draft"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_campaigns_user_id", "campaigns", ["user_id"])
        op.create_index("ix_campaigns_client_id", "campaigns", ["client_id"])


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if "campaigns" in insp.get_table_names():
        op.drop_table("campaigns")
