"""ISSUE-224 (M4 Inventory): vendor returns — add the ``supplier_credit_ledger`` table.

Backs vendor returns / supplier credit notes: when a merchant returns received
goods to a vendor, the returned value is appended here as a signed credit-note row
with the resulting ``balance_after``, so a supplier's outstanding credit balance is
reconstructable and every return is auditable. Mirrors ``store_credit_ledger``.

On a fresh database the baseline revision's ``create_all`` already builds this table
at its current shape, so the create is guarded to be idempotent — it only acts on a
database that was migrated to head before this revision existed.

Revision ID: 224scn0a1b2c
Revises: 223bat0a1b2c
Create Date: 2026-06-30 23:55:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "224scn0a1b2c"
down_revision: Union[str, Sequence[str], None] = "223bat0a1b2c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if "supplier_credit_ledger" not in insp.get_table_names():
        op.create_table(
            "supplier_credit_ledger",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("client_id", sa.Integer(), nullable=True),
            sa.Column("supplier_id", sa.Integer(), nullable=False),
            sa.Column("entry_type", sa.String(), nullable=False),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("balance_after", sa.Numeric(12, 2), nullable=False),
            sa.Column("purchase_order_id", sa.Integer(), nullable=True),
            sa.Column("note", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index(
            "ix_supplier_credit_ledger_user_id", "supplier_credit_ledger", ["user_id"]
        )
        op.create_index(
            "ix_supplier_credit_ledger_client_id", "supplier_credit_ledger", ["client_id"]
        )
        op.create_index(
            "ix_supplier_credit_ledger_supplier_id",
            "supplier_credit_ledger",
            ["supplier_id"],
        )
        op.create_index(
            "ix_supplier_credit_ledger_purchase_order_id",
            "supplier_credit_ledger",
            ["purchase_order_id"],
        )


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if "supplier_credit_ledger" in insp.get_table_names():
        op.drop_index(
            "ix_supplier_credit_ledger_purchase_order_id",
            table_name="supplier_credit_ledger",
        )
        op.drop_index(
            "ix_supplier_credit_ledger_supplier_id", table_name="supplier_credit_ledger"
        )
        op.drop_index(
            "ix_supplier_credit_ledger_client_id", table_name="supplier_credit_ledger"
        )
        op.drop_index(
            "ix_supplier_credit_ledger_user_id", table_name="supplier_credit_ledger"
        )
        op.drop_table("supplier_credit_ledger")
