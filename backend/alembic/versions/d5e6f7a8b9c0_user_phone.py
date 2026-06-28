"""#203 / parity #4: add ``users.phone`` for profile editing.

Profile editing (name / email / phone) wires the ``UserProfile`` page to
``GET/PUT /users/profile``. Name and email already live on ``users``; this adds
the optional contact ``phone`` column so all three can persist.

On a fresh database the model metadata already builds ``users`` with the column
(``create_all``), so the add is guarded to be idempotent.

Revision ID: d5e6f7a8b9c0
Revises: c4e5f6a7b8d9
Create Date: 2026-06-28 12:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, Sequence[str], None] = "c4e5f6a7b8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "users"
_COLUMN = "phone"


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if _TABLE not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    if _COLUMN not in existing:
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(length=50), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if _TABLE not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    if _COLUMN in existing:
        op.drop_column(_TABLE, _COLUMN)
