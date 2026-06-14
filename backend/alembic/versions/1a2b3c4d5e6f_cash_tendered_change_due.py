"""ISSUE-074: cash-drawer change helper — add transactions.cash_tendered/change_due.

Adds ``transactions.cash_tendered`` (the cash the customer handed over on a cash
payment) and ``transactions.change_due`` (the change owed back). These are
**drawer-facing only** — the captured tender still covers the amount due, so they
never change ``subtotal``/``vat_amount``/``total_amount`` or gross sales. Both are
null on a non-cash sale or when the cashier did not record a tendered amount.

On a fresh database the baseline revision's ``create_all`` already builds the
``transactions`` table at its current shape (with the new columns), so the adds
are guarded to be idempotent — they only act on a database migrated to head
before this revision existed (mirrors a6b7c8d9e0f1 / tip_amount).

Revision ID: 1a2b3c4d5e6f
Revises: 06af1b2c3d4e
Create Date: 2026-06-14 23:30:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "1a2b3c4d5e6f"
down_revision: Union[str, Sequence[str], None] = "06af1b2c3d4e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_column_if_missing(insp, table: str, column: str) -> None:
    if table not in insp.get_table_names():
        # Fresh DB: the baseline revision's create_all already built the table at
        # its current shape (with the new column). Nothing to backfill.
        return
    existing = {c["name"] for c in insp.get_columns(table)}
    if column not in existing:
        op.add_column(table, sa.Column(column, sa.Float(), nullable=True))


def _drop_column_if_present(insp, table: str, column: str) -> None:
    if table in insp.get_table_names():
        existing = {c["name"] for c in insp.get_columns(table)}
        if column in existing:
            op.drop_column(table, column)


def upgrade() -> None:
    insp = inspect(op.get_bind())
    _add_column_if_missing(insp, "transactions", "cash_tendered")
    _add_column_if_missing(insp, "transactions", "change_due")


def downgrade() -> None:
    insp = inspect(op.get_bind())
    _drop_column_if_present(insp, "transactions", "change_due")
    _drop_column_if_present(insp, "transactions", "cash_tendered")
