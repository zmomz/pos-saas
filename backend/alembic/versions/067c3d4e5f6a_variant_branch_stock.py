"""ISSUE-067 (INV-03 × INV-04): per-branch variant stock ledger.

Adds the ``variant_branch_stock`` table — one row per (client, branch, variant)
holding that branch's on-hand quantity of the variant. A branch-tagged variant
sale draws from this ledger instead of the variant's client-level façade
quantity (``services.variant_branch_stock``), so a sale in branch A never touches
branch B's level. Existing client-level variant totals are left untouched — the
ledger seeds lazily from them the first time a branch transacts a variant, so no
data is lost.

On a fresh database the baseline ``create_all`` already builds the table at its
current shape, so the create is guarded to be idempotent — it only builds the
table on a database migrated to head before this revision existed.

Revision ID: 067c3d4e5f6a
Revises: 066b2c3d4e5f
Create Date: 2026-06-14 17:25:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "067c3d4e5f6a"
down_revision: Union[str, Sequence[str], None] = "066b2c3d4e5f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if "variant_branch_stock" in insp.get_table_names():
        return
    op.create_table(
        "variant_branch_stock",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=False),
        sa.Column("branch_id", sa.Integer(), nullable=False),
        sa.Column("variant_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "client_id", "branch_id", "variant_id", name="uq_variant_branch_stock"
        ),
    )
    op.create_index(
        "ix_variant_branch_stock_id", "variant_branch_stock", ["id"]
    )


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if "variant_branch_stock" in insp.get_table_names():
        op.drop_table("variant_branch_stock")
