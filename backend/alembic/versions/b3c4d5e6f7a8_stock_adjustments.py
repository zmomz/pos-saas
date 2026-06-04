"""F-036 / INV-06: stock counts & adjustments with reasons → variance.

Adds the ``stock_adjustments`` table — the variance record a merchant leaves when
reconciling on-hand against a physical count or recording wastage/damage. A row
snapshots the system on-hand, the new counted figure, and ``variance = counted −
system`` alongside a reason; applying it sets the stock pool (per-branch ledger when
``branch_id`` is set, else the client-level product quantity).

On a fresh database the baseline revision's ``create_all`` already builds this table
at its current shape, so the create is guarded to be idempotent — it only acts on a
database that was migrated to head before this revision existed. See finding F-036.

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-06-04 10:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, Sequence[str], None] = "a2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if "stock_adjustments" not in insp.get_table_names():
        op.create_table(
            "stock_adjustments",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("client_id", sa.Integer(), nullable=True),
            sa.Column("branch_id", sa.Integer(), nullable=True),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("product_name", sa.String(), nullable=True),
            sa.Column("reason", sa.String(), nullable=False, server_default="count"),
            sa.Column("system_quantity", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("counted_quantity", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("variance", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("note", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_stock_adjustments_user_id", "stock_adjustments", ["user_id"])
        op.create_index("ix_stock_adjustments_client_id", "stock_adjustments", ["client_id"])


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if "stock_adjustments" in insp.get_table_names():
        op.drop_index("ix_stock_adjustments_client_id", table_name="stock_adjustments")
        op.drop_index("ix_stock_adjustments_user_id", table_name="stock_adjustments")
        op.drop_table("stock_adjustments")
