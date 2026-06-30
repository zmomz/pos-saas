"""ISSUE-223 (M4 Product): digital products — add products.is_digital.

Adds an optional ``is_digital`` boolean flag: a product with no physical stock
(an e-voucher, top-up, licence or download). Because there is no on-hand
inventory to deplete, a digital product can never be "low" and is never an
auto-reorder candidate, so it is excluded from the low-stock list and the
reorder-suggestions surface. NULL (legacy rows) is treated as physical.

On a fresh database the baseline revision's ``create_all`` already builds the
``products`` table at its current shape (with the new column), so the add is
guarded to be idempotent — it only acts on a database migrated to head before
this revision existed. Mirrors the brand/manufacturer revision (223brm9a1b2c).

Revision ID: 223dig0a1b2c
Revises: 223brm9a1b2c
Create Date: 2026-06-30 23:20:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "223dig0a1b2c"
down_revision: Union[str, Sequence[str], None] = "223brm9a1b2c"
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
            sa.Column(
                column,
                sa.Boolean(),
                nullable=True,
                server_default=sa.text("false"),
            ),
        )


def _drop_column_if_present(insp, table: str, column: str) -> None:
    if table in insp.get_table_names():
        existing = {c["name"] for c in insp.get_columns(table)}
        if column in existing:
            op.drop_column(table, column)


def upgrade() -> None:
    insp = inspect(op.get_bind())
    _add_column_if_missing(insp, "products", "is_digital")


def downgrade() -> None:
    insp = inspect(op.get_bind())
    _drop_column_if_present(insp, "products", "is_digital")
