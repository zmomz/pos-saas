"""M5·CRM / issue-221: per-customer notes thread.

Adds the ``customer_notes`` table — an append-only, timestamped note attached to a
customer (the running log behind the single ``customers.notes`` snapshot).

On a fresh database the baseline revision's ``create_all`` already builds the table
at its current shape, so the create is guarded idempotently — it only acts on a
database migrated to head before this revision existed.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a8b9
Create Date: 2026-06-30 22:20:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if "customer_notes" not in insp.get_table_names():
        op.create_table(
            "customer_notes",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("client_id", sa.Integer(), nullable=True),
            sa.Column("customer_id", sa.Integer(), nullable=False),
            sa.Column("body", sa.String(), nullable=False),
            sa.Column("author", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_customer_notes_user_id", "customer_notes", ["user_id"])
        op.create_index("ix_customer_notes_client_id", "customer_notes", ["client_id"])
        op.create_index("ix_customer_notes_customer_id", "customer_notes", ["customer_id"])


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if "customer_notes" in insp.get_table_names():
        op.drop_table("customer_notes")
