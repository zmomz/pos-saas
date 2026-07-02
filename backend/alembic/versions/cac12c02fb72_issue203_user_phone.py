"""#203 (M1·Auth, parity #4): add ``users.phone`` for self-service profile editing.

Users can now edit their own name/email/phone on the profile screen. ``name`` and
``email`` already exist on ``users``; this adds the new nullable ``phone`` column.

On a fresh database the baseline ``create_all`` already builds ``users`` with the
column, so the add is guarded to be idempotent — it only backfills a database
migrated to head before this revision existed.

Revision ID: cac12c02fb72
Revises: 9d2a8af2fa93
Create Date: 2026-06-30 14:45:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "cac12c02fb72"
down_revision: Union[str, Sequence[str], None] = "9d2a8af2fa93"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "users"
_COLUMN = "phone"


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if _TABLE not in insp.get_table_names():
        # Fresh DB: create_all already built the table with this column.
        return
    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    if _COLUMN not in existing:
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(length=50), nullable=True))


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if _TABLE not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    if _COLUMN in existing:
        op.drop_column(_TABLE, _COLUMN)
