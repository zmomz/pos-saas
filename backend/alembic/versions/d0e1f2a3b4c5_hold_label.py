"""F-010 / POS-10: park/hold & recall — add transactions.hold_label.

Adds ``transactions.hold_label``, the cashier-facing label of a parked
(``status="held"``) ticket. A held row persists a cart without any fiscal side
effect (no invoice counter, no ZATCA stamp, excluded from sales reporting) so a
cashier can suspend a sale and run multiple concurrent open tickets, then recall
one to resume it. The label tells those concurrent tickets apart on recall.

On a fresh database the baseline revision's ``create_all`` already builds the
``transactions`` table at its current shape (with the new column), so the add is
guarded to be idempotent — it only acts on a database migrated to head before
this revision existed. See finding F-010.

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-06-04 10:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "d0e1f2a3b4c5"
down_revision: Union[str, Sequence[str], None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_column_if_missing(insp, table: str, column: str) -> None:
    if table not in insp.get_table_names():
        # Fresh DB: the baseline revision's create_all already built the table at
        # its current shape (with the new column). Nothing to backfill.
        return
    existing = {c["name"] for c in insp.get_columns(table)}
    if column not in existing:
        op.add_column(table, sa.Column(column, sa.String(), nullable=True))


def _drop_column_if_present(insp, table: str, column: str) -> None:
    if table in insp.get_table_names():
        existing = {c["name"] for c in insp.get_columns(table)}
        if column in existing:
            op.drop_column(table, column)


def upgrade() -> None:
    insp = inspect(op.get_bind())
    _add_column_if_missing(insp, "transactions", "hold_label")


def downgrade() -> None:
    insp = inspect(op.get_bind())
    _drop_column_if_present(insp, "transactions", "hold_label")
