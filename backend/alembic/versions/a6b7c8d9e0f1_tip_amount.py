"""F-012 / POS-13: tips capture — add transactions.tip_amount.

Adds ``transactions.tip_amount``, the gratuity collected on a sale on top of the
invoice total. A tip is **outside the VAT base** (it is not part of the taxable
supply) so it never changes ``subtotal``/``vat_amount``/``total_amount`` (the
ZATCA tax-invoice total stays goods+VAT) — it is recorded separately, added to
the amount actually charged across the tenders, surfaced on the receipt as the
amount paid, and reported per shift in the Z/X-report.

On a fresh database the baseline revision's ``create_all`` already builds the
``transactions`` table at its current shape (with the new column), so the add is
guarded to be idempotent — it only acts on a database migrated to head before
this revision existed. See finding F-012.

Revision ID: a6b7c8d9e0f1
Revises: a5b6c7d8e9f0
Create Date: 2026-06-05 10:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "a6b7c8d9e0f1"
down_revision: Union[str, Sequence[str], None] = "a5b6c7d8e9f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_column_if_missing(insp, table: str, column: str) -> None:
    if table not in insp.get_table_names():
        # Fresh DB: the baseline revision's create_all already built the table at
        # its current shape (with the new column). Nothing to backfill.
        return
    existing = {c["name"] for c in insp.get_columns(table)}
    if column not in existing:
        op.add_column(
            table,
            sa.Column(column, sa.Float(), nullable=True, server_default="0"),
        )


def _drop_column_if_present(insp, table: str, column: str) -> None:
    if table in insp.get_table_names():
        existing = {c["name"] for c in insp.get_columns(table)}
        if column in existing:
            op.drop_column(table, column)


def upgrade() -> None:
    insp = inspect(op.get_bind())
    _add_column_if_missing(insp, "transactions", "tip_amount")


def downgrade() -> None:
    insp = inspect(op.get_bind())
    _drop_column_if_present(insp, "transactions", "tip_amount")
