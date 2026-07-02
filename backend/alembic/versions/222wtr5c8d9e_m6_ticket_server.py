"""M6·Restaurant / issue-222: order-ticket waiter (server) assignment.

Adds ``order_tickets.server_id`` + ``order_tickets.server_name`` — the staff
member currently serving the ticket's section, set by the "transfer waiter" flow
(F-045). ``server_id`` references the owner's own ``staff_members`` row;
``server_name`` snapshots the name so the floor renders without a join.

On a fresh database the baseline revision's ``create_all`` already builds the
columns at their current shape, so the adds are guarded idempotently — they only
act on a database migrated to head before this revision existed.

Revision ID: 222wtr5c8d9e
Revises: 221dob5a6b7c
Create Date: 2026-06-30 23:10:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "222wtr5c8d9e"
down_revision: Union[str, Sequence[str], None] = "221dob5a6b7c"
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
        insp, "order_tickets", sa.Column("server_id", sa.Integer(), nullable=True)
    )
    _add_column_if_missing(
        insp, "order_tickets", sa.Column("server_name", sa.String(), nullable=True)
    )


def downgrade() -> None:
    insp = inspect(op.get_bind())
    _drop_column_if_present(insp, "order_tickets", "server_name")
    _drop_column_if_present(insp, "order_tickets", "server_id")
