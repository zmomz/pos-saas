"""M5·CRM / issue-221: customer date of birth (birthday rewards).

Adds the ``customers.date_of_birth`` column — the customer's birthday, matched
(month/day) by the birthday-reward batch to grant store credit on their birthday.

On a fresh database the baseline revision's ``create_all`` already builds the column
at its current shape, so the add is guarded idempotently — it only acts on a
database migrated to head before this revision existed.

Revision ID: 221dob5a6b7c
Revises: a8e78357df4d
Create Date: 2026-06-30 22:55:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "221dob5a6b7c"
down_revision: Union[str, Sequence[str], None] = "a8e78357df4d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_column_if_missing(insp, table: str, column: sa.Column) -> None:
    if table not in insp.get_table_names():
        # Fresh DB: create_all already built the table at its current shape.
        return
    existing = {c["name"] for c in insp.get_columns(table)}
    if column.name not in existing:
        op.add_column(table, column)


def _drop_column_if_present(insp, table: str, column: str) -> None:
    if table in insp.get_table_names():
        existing = {c["name"] for c in insp.get_columns(table)}
        if column in existing:
            # Drop any index covering this column first — SQLite rejects a
            # DROP COLUMN while an index still references it (the column can be
            # indexed via the ORM's ``index=True`` baked into a create_table).
            # Re-inspect live so an index a prior step already dropped is not
            # dropped twice (a passed-in inspector may be stale).
            for idx in inspect(op.get_bind()).get_indexes(table):
                if column in (idx.get("column_names") or []):
                    op.drop_index(idx["name"], table_name=table)
            op.drop_column(table, column)


def upgrade() -> None:
    insp = inspect(op.get_bind())
    _add_column_if_missing(
        insp, "customers", sa.Column("date_of_birth", sa.Date(), nullable=True)
    )


def downgrade() -> None:
    insp = inspect(op.get_bind())
    _drop_column_if_present(insp, "customers", "date_of_birth")
