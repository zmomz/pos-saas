"""F-032 / INV-05: inter-branch stock transfers.

Adds the ``stock_transfers`` audit table backing the Branch Management "Transfer
Stock" dialog, which previously POSTed to a non-existent route (a dead-end UI). A
row records a completed inter-branch move (source−N / dest+N on the per-branch
``product_branch_stock`` ledger), so the movement is traceable.

On a fresh database the baseline revision's ``create_all`` already builds this table
at its current shape, so the create is guarded to be idempotent — it only acts on a
database that was migrated to head before this revision existed. See finding F-032.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-03 19:30:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if "stock_transfers" not in insp.get_table_names():
        op.create_table(
            "stock_transfers",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("client_id", sa.Integer(), nullable=True),
            sa.Column("from_branch_id", sa.Integer(), nullable=False),
            sa.Column("to_branch_id", sa.Integer(), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("product_name", sa.String(), nullable=True),
            sa.Column("quantity", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(), nullable=False, server_default="received"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_stock_transfers_user_id", "stock_transfers", ["user_id"])
        op.create_index("ix_stock_transfers_client_id", "stock_transfers", ["client_id"])


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if "stock_transfers" in insp.get_table_names():
        op.drop_table("stock_transfers")
