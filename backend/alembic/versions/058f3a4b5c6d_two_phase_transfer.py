"""ISSUE-061: two-phase stock transfer — receive bookkeeping columns.

Adds two nullable columns to ``stock_transfers``:
- ``received_quantity`` — the quantity actually booked in at the destination when
  a two-phase transfer is received (null for a one-step transfer and while a
  two-phase transfer is still ``in_transit``).
- ``discrepancy`` — the dispatched−received shortfall recorded on receive
  (in-transit shrink).

On a fresh database the baseline ``create_all`` already builds the table at its
current shape (with the columns), so the adds are guarded to be idempotent — they
only backfill a database migrated to head before this revision existed.

Revision ID: 058f3a4b5c6d
Revises: 057e2f3a4b5c
Create Date: 2026-06-14 09:20:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "058f3a4b5c6d"
down_revision: Union[str, Sequence[str], None] = "057e2f3a4b5c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "stock_transfers"
_COLUMNS = ("received_quantity", "discrepancy")


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if _TABLE not in insp.get_table_names():
        # Fresh DB: create_all already built the table with these columns.
        return
    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    for column in _COLUMNS:
        if column not in existing:
            op.add_column(_TABLE, sa.Column(column, sa.Integer(), nullable=True))


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if _TABLE not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    for column in _COLUMNS:
        if column in existing:
            op.drop_column(_TABLE, column)
