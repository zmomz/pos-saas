"""F-071 / RPT-08: persist the applied discount code on the sale.

Adds ``transactions.discount_code`` — the promo code (PRC-01) applied to a sale,
persisted so the discount report (``/reports/discounts``) can show *which* code was
used and by whom. Null for a manual (codeless) ``pos.discount`` override and for
sales with no discount; purely additive, it never touches the sale's monetary
totals, stock or fiscal stamp.

On a fresh database the baseline revision's ``create_all`` already builds the
``transactions`` table at its current shape (with the new column), so the add is
guarded to be idempotent — it only acts on a database migrated to head before this
revision existed. See finding F-071.

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-06-05 17:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, Sequence[str], None] = "d6e7f8a9b0c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_column_if_missing(insp, table: str, column: sa.Column) -> None:
    if table not in insp.get_table_names():
        # Fresh DB: the baseline create_all already built the table with the column.
        return
    existing = {c["name"] for c in insp.get_columns(table)}
    if column.name not in existing:
        op.add_column(table, column)


def _drop_column_if_present(insp, table: str, column: str) -> None:
    if table in insp.get_table_names():
        existing = {c["name"] for c in insp.get_columns(table)}
        if column in existing:
            op.drop_column(table, column)


def upgrade() -> None:
    insp = inspect(op.get_bind())
    _add_column_if_missing(
        insp, "transactions", sa.Column("discount_code", sa.String(), nullable=True)
    )


def downgrade() -> None:
    insp = inspect(op.get_bind())
    _drop_column_if_present(insp, "transactions", "discount_code")
