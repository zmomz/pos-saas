"""ISSUE-032: combo line expansion — add order_ticket_items.combo_id.

A combo/bundle line is rung up with ``product_id=None`` and priced at the combo's
bundle price. Without a reference back to the combo, the settle path cannot expand
the line into its component products, so selling a combo charged the bundle but
decremented **no** stock (silent oversell, finding H23). This adds ``combo_id`` so
settle can recover the combo and deduct each component exactly once.

On a fresh database the baseline revision's ``create_all`` already builds the
``order_ticket_items`` table at its current shape (with the column), so the add is
guarded to be idempotent — it only backfills a database migrated to head before
this revision existed.

Revision ID: b0c1d2e3f4a5
Revises: a9b0c1d2e3f4
Create Date: 2026-06-14 02:20:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "b0c1d2e3f4a5"
down_revision: Union[str, Sequence[str], None] = "a9b0c1d2e3f4"
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
    _add_column_if_missing(
        insp, "order_ticket_items", sa.Column("combo_id", sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    insp = inspect(op.get_bind())
    _drop_column_if_present(insp, "order_ticket_items", "combo_id")
