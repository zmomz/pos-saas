"""ISSUE-019: append-only / tamper-evident audit log — hash-chain columns.

Adds two nullable columns to ``audit_logs``:
- ``prev_hash`` — the preceding row's ``row_hash`` (a genesis constant for the
  first row), linking each row to its predecessor.
- ``row_hash`` — sha256(prev_hash + canonical row content); re-derivable by
  ``services.audit.verify_audit_chain`` so a mutated or removed row is detectable.

On a fresh database the baseline ``create_all`` already builds the table with
these columns, so the adds are guarded to be idempotent — they only backfill a
database migrated to head before this revision existed. Pre-existing rows keep
NULL hashes (they predate the chain) and are skipped by verification.

Revision ID: 059a4b5c6d7e
Revises: 058f3a4b5c6d
Create Date: 2026-06-14 10:30:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "059a4b5c6d7e"
down_revision: Union[str, Sequence[str], None] = "058f3a4b5c6d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "audit_logs"
_COLUMNS = ("prev_hash", "row_hash")


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if _TABLE not in insp.get_table_names():
        # Fresh DB: create_all already built the table with these columns.
        return
    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    for column in _COLUMNS:
        if column not in existing:
            op.add_column(_TABLE, sa.Column(column, sa.String(), nullable=True))
    if "row_hash" not in existing:
        op.create_index("ix_audit_logs_row_hash", _TABLE, ["row_hash"])


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if _TABLE not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    if "row_hash" in existing:
        op.drop_index("ix_audit_logs_row_hash", table_name=_TABLE)
    for column in _COLUMNS:
        if column in existing:
            op.drop_column(_TABLE, column)
