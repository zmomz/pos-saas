"""ISSUE-056: quote→sale conversion — link a converted quotation to its sale.

Adds one nullable column to ``quotations``:
- ``converted_transaction_id`` — the id of the fiscal sale this quote was
  converted into (set once, when the quote moves to the terminal ``converted``
  status). Null for any quote that hasn't been converted.

On a fresh database the baseline revision's ``create_all`` already builds the
table at its current shape (with the column), so the add is guarded to be
idempotent — it only backfills a database migrated to head before this revision
existed.

Revision ID: 056d1e2f3a4b
Revises: 054c0a1b2c3d
Create Date: 2026-06-14 06:20:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "056d1e2f3a4b"
down_revision: Union[str, Sequence[str], None] = "054c0a1b2c3d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "quotations"
_COLUMN = "converted_transaction_id"


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if _TABLE not in insp.get_table_names():
        # Fresh DB: create_all already built the table with this column.
        return
    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    if _COLUMN not in existing:
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.Integer(), nullable=True))


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if _TABLE not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    if _COLUMN in existing:
        op.drop_column(_TABLE, _COLUMN)
