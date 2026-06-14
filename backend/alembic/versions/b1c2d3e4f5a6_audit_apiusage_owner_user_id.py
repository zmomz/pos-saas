"""ISSUE-012: owner-scope audit/api-usage — add ``owner_user_id`` tag.

Adds ``audit_logs.owner_user_id`` and ``api_usage.owner_user_id``: the owning
merchant a row belongs to, resolved via the tenant scope. The write-path
middleware tags each row with the owner so a merchant's audit/usage query
surfaces all their staff's activity (finding H4); reads scope on this column
instead of the raw actor id. Nullable so existing rows (and master/anonymous
writes) are unaffected.

On a fresh database the baseline revision's ``create_all`` already builds both
tables at their current shape (with the column), so the add is guarded to be
idempotent — it only backfills a database migrated to head before this revision
existed.

Revision ID: b1c2d3e4f5a6
Revises: c6d7e8f9a0b1
Create Date: 2026-06-14 04:30:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "c6d7e8f9a0b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("audit_logs", "api_usage")
_COLUMN = "owner_user_id"


def _add_column_if_missing(insp, table: str, column: str) -> None:
    if table not in insp.get_table_names():
        # Fresh DB: the baseline revision's create_all already built the table at
        # its current shape (with the new column). Nothing to backfill.
        return
    existing = {c["name"] for c in insp.get_columns(table)}
    if column not in existing:
        op.add_column(table, sa.Column(column, sa.String(), nullable=True))
        op.create_index(f"ix_{table}_{column}", table, [column])


def _drop_column_if_present(insp, table: str, column: str) -> None:
    if table in insp.get_table_names():
        existing = {c["name"] for c in insp.get_columns(table)}
        if column in existing:
            try:
                op.drop_index(f"ix_{table}_{column}", table_name=table)
            except Exception:
                pass
            op.drop_column(table, column)


def upgrade() -> None:
    insp = inspect(op.get_bind())
    for table in _TABLES:
        _add_column_if_missing(insp, table, _COLUMN)


def downgrade() -> None:
    insp = inspect(op.get_bind())
    for table in _TABLES:
        _drop_column_if_present(insp, table, _COLUMN)
