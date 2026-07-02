"""ISSUE-070 (P2 restaurant): per-seat / partial settlement —
add order_ticket_items.settled_at.

Marks a ticket line that a prior partial settlement already billed into its own
fiscal invoice. NULL = the line is still on the unpaid remainder; the check / split
/ settle paths only ever consider unpaid lines, so a line is never double-billed.

On a fresh database the baseline revision's ``create_all`` already builds the
``order_ticket_items`` table at its current shape (with the new column), so the add
is guarded to be idempotent — it only acts on a database migrated to head before
this revision existed. Mirrors the product image_url revision (069e5f6a7b8c).

Revision ID: 06af1b2c3d4e
Revises: 069e5f6a7b8c
Create Date: 2026-06-14 22:45:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "06af1b2c3d4e"
down_revision: Union[str, Sequence[str], None] = "069e5f6a7b8c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_column_if_missing(insp, table: str, column: str) -> None:
    if table not in insp.get_table_names():
        # Fresh DB: the baseline revision's create_all already built the table at
        # its current shape (with the new column). Nothing to backfill.
        return
    existing = {c["name"] for c in insp.get_columns(table)}
    if column not in existing:
        op.add_column(table, sa.Column(column, sa.DateTime(timezone=True), nullable=True))


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
    _add_column_if_missing(insp, "order_ticket_items", "settled_at")


def downgrade() -> None:
    insp = inspect(op.get_bind())
    _drop_column_if_present(insp, "order_ticket_items", "settled_at")
