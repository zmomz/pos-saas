"""ISSUE-034: drop the redundant ``permissions.role`` column.

A ``permissions`` row is a per-user override keyed by ``(user_id,
permission_key)``; the role-driven defaults now live in code
(``dependencies.permissions.ROLE_PERMISSIONS``), so the NOT-NULL ``role`` column
was never read by enforcement and is dropped.

On a fresh database the baseline ``create_all`` already builds the table at its
current (role-less) shape, so the drop is guarded to be idempotent — it only
rewrites a database migrated to head before this revision existed.

Revision ID: 062d9e0f1a2b
Revises: 061c7e8f9a0b
Create Date: 2026-06-14 11:25:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "062d9e0f1a2b"
down_revision: Union[str, Sequence[str], None] = "061c7e8f9a0b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "permissions"
_COLUMN = "role"


def _has_column(insp) -> bool:
    return _TABLE in insp.get_table_names() and any(
        c["name"] == _COLUMN for c in insp.get_columns(_TABLE)
    )


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if not _has_column(insp):
        # Fresh DB: create_all already built the role-less table.
        return
    with op.batch_alter_table(_TABLE) as batch:
        batch.drop_column(_COLUMN)


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if _TABLE not in insp.get_table_names() or _has_column(insp):
        return
    # Re-add as nullable: legacy rows have no role to backfill.
    with op.batch_alter_table(_TABLE) as batch:
        batch.add_column(sa.Column(_COLUMN, sa.String(), nullable=True))
