"""F-035 / INV-08: reorder points — add products.reorder_point + reorder_quantity.

Adds two per-product columns:

- ``reorder_point`` — the on-hand threshold at or below which the product is
  flagged low-stock and suggested for a purchase order. ``0``/NULL means the
  product has no explicit reorder point and falls back to the fixed default
  threshold used by the low-stock endpoints (legacy behaviour).
- ``reorder_quantity`` — the order amount the auto-PO suggestion proposes when
  the product is triggered. ``0``/NULL means "bring stock back up to the
  reorder point".

On a fresh database the baseline revision's ``create_all`` already builds the
``products`` table at its current shape (with the new columns), so the add is
guarded to be idempotent — it only acts on a database migrated to head before
this revision existed. See finding F-035.

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-06-04 12:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, Sequence[str], None] = "b3c4d5e6f7a8"
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
            sa.Column(column, sa.Integer(), nullable=True, server_default="0"),
        )


def _drop_column_if_present(insp, table: str, column: str) -> None:
    if table in insp.get_table_names():
        existing = {c["name"] for c in insp.get_columns(table)}
        if column in existing:
            op.drop_column(table, column)


def upgrade() -> None:
    insp = inspect(op.get_bind())
    _add_column_if_missing(insp, "products", "reorder_point")
    _add_column_if_missing(insp, "products", "reorder_quantity")


def downgrade() -> None:
    insp = inspect(op.get_bind())
    _drop_column_if_present(insp, "products", "reorder_quantity")
    _drop_column_if_present(insp, "products", "reorder_point")
