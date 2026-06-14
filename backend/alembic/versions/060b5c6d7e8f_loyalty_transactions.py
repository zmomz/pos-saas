"""ISSUE-028: loyalty point-movement ledger table.

Adds ``loyalty_transactions`` — the append-only ledger behind the loyalty admin
page's "Points History" tab and the ``/loyalty/adjust`` endpoint.

On a fresh database the baseline ``create_all`` already builds the table at its
current shape, so the create is guarded to be idempotent — it only backfills a
database migrated to head before this revision existed.

Revision ID: 060b5c6d7e8f
Revises: 059a4b5c6d7e
Create Date: 2026-06-14 10:55:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "060b5c6d7e8f"
down_revision: Union[str, Sequence[str], None] = "059a4b5c6d7e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "loyalty_transactions"


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if _TABLE in insp.get_table_names():
        # Fresh DB: create_all already built the table at the current shape.
        return
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=True),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(f"ix_{_TABLE}_user_id", _TABLE, ["user_id"])
    op.create_index(f"ix_{_TABLE}_customer_id", _TABLE, ["customer_id"])
    op.create_index(f"ix_{_TABLE}_id", _TABLE, ["id"])


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if _TABLE not in insp.get_table_names():
        return
    op.drop_table(_TABLE)
