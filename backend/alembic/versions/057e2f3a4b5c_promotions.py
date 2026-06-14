"""ISSUE-058: advanced discounts — the ``promotions`` table.

Creates the ``promotions`` table backing auto-applied line/category/BOGO
promotions. Unlike a coded ``discounts`` row, a promotion targets part of the cart
and fires on its own when the cart meets ``min_subtotal``.

On a fresh database the baseline ``create_all`` already builds the table at its
current shape, so the create is guarded to be idempotent — it only builds the
table on a database migrated to head before this revision existed.

Revision ID: 057e2f3a4b5c
Revises: 056d1e2f3a4b
Create Date: 2026-06-14 07:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "057e2f3a4b5c"
down_revision: Union[str, Sequence[str], None] = "056d1e2f3a4b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "promotions"


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if _TABLE in insp.get_table_names():
        # Fresh DB: create_all already built the table.
        return
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("disc_type", sa.String(), nullable=True),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("min_subtotal", sa.Float(), nullable=True),
        sa.Column("bogo_buy_qty", sa.Integer(), nullable=True),
        sa.Column("bogo_get_qty", sa.Integer(), nullable=True),
        sa.Column("bogo_get_percent", sa.Float(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(f"ix_{_TABLE}_user_id", _TABLE, ["user_id"])
    op.create_index(f"ix_{_TABLE}_id", _TABLE, ["id"])


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if _TABLE not in insp.get_table_names():
        return
    op.drop_table(_TABLE)
