"""M5·CRM / issue-221: customer blacklist — ``customers.blacklisted_at`` + reason.

Adds two columns to ``customers``:
- ``blacklisted_at`` (timestamp, nullable): when set, the customer has been
  blacklisted and is barred from transacting — the POS rejects a sale that
  identifies them (403). NULL ⇒ in good standing.
- ``blacklist_reason`` (string, nullable): why they were blocked (chargeback
  fraud, abuse, …), kept for the audit trail.

On a fresh database the baseline revision's ``create_all`` already builds the
``customers`` table at its current shape (with both columns), so each add is
guarded idempotently — it only acts on a database migrated to head before this
revision existed.

Revision ID: a1b2c3d4e5f7
Revises: cac12c02fb72
Create Date: 2026-06-30 22:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f7"
down_revision: Union[str, Sequence[str], None] = "cac12c02fb72"
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
        insp, "customers", sa.Column("blacklisted_at", sa.DateTime(timezone=True), nullable=True)
    )
    _add_column_if_missing(
        insp, "customers", sa.Column("blacklist_reason", sa.String(), nullable=True)
    )


def downgrade() -> None:
    insp = inspect(op.get_bind())
    _drop_column_if_present(insp, "customers", "blacklist_reason")
    _drop_column_if_present(insp, "customers", "blacklisted_at")
