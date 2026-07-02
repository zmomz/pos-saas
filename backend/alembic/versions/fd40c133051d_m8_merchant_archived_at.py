"""M8 / issue-215: merchant lifecycle — archive/restore via ``clients.archived_at``.

Adds one column to ``clients``:
- ``archived_at`` (ISO timestamp string, nullable): when set, the merchant has
  been *archived* by its owning agent. An archived merchant is hidden from the
  agent's active book, blocked at authentication (distinct from the ``is_active``
  non-payment suspension), and its slot is freed back to the agent's quota — but
  all of its data is retained so a *restore* reverses the state with no data loss.
  The timestamp also anchors the post-retention delete window. NULL ⇒ live.

On a fresh database the baseline revision's ``create_all`` already builds the
``clients`` table at its current shape (with the new column), so the add is
guarded idempotently — it only acts on a database migrated to head before this
revision existed.

Revision ID: fd40c133051d
Revises: b01d4ddbe7e5
Create Date: 2026-06-30 12:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "fd40c133051d"
down_revision: Union[str, Sequence[str], None] = "b01d4ddbe7e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_column_if_missing(insp, table: str, column: sa.Column) -> None:
    if table not in insp.get_table_names():
        # Fresh DB: the baseline revision's create_all already built the table at
        # its current shape (with the new column). Nothing to backfill.
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
    _add_column_if_missing(insp, "clients", sa.Column("archived_at", sa.String(), nullable=True))


def downgrade() -> None:
    insp = inspect(op.get_bind())
    _drop_column_if_present(insp, "clients", "archived_at")
