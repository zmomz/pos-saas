"""ISSUE-044: configurable loyalty points-expiry policy.

Adds ``loyalty_programs.points_expiry_days`` — the number of days after which
earned points age out (NULL/0 = never). The usable balance is derived from the
``loyalty_transactions`` ledger relative to this window.

On a fresh database the baseline ``create_all`` already builds the column at its
current shape, so the add is guarded to be idempotent — it only backfills a
database migrated to head before this revision existed.

Revision ID: 063e0f1a2b3c
Revises: 062d9e0f1a2b
Create Date: 2026-06-14 13:40:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "063e0f1a2b3c"
down_revision: Union[str, Sequence[str], None] = "062d9e0f1a2b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "loyalty_programs"
_COLUMN = "points_expiry_days"


def upgrade() -> None:
    insp = inspect(op.get_bind())
    cols = {c["name"] for c in insp.get_columns(_TABLE)}
    if _COLUMN in cols:
        # Fresh DB: create_all already built the column at the current shape.
        return
    op.add_column(_TABLE, sa.Column(_COLUMN, sa.Integer(), nullable=True))


def downgrade() -> None:
    insp = inspect(op.get_bind())
    cols = {c["name"] for c in insp.get_columns(_TABLE)}
    if _COLUMN not in cols:
        return
    op.drop_column(_TABLE, _COLUMN)
