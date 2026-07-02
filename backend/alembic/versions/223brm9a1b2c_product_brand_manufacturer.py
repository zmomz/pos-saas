"""ISSUE-223 (M4 Product): brand / manufacturer — add products.brand + manufacturer.

Adds two optional free-text catalog fields: ``brand`` (the marketing name a
shopper recognises, e.g. "Panadol") and ``manufacturer`` (the legal maker, which
differs from the brand in pharmacy/electronics verticals, e.g. maker "GSK"). NULL
means "unspecified".

On a fresh database the baseline revision's ``create_all`` already builds the
``products`` table at its current shape (with the new columns), so each add is
guarded to be idempotent — it only acts on a database migrated to head before
this revision existed. Mirrors the image_url revision (069e5f6a7b8c).

Revision ID: 223brm9a1b2c
Revises: 222crs8f4c5d
Create Date: 2026-06-30 23:10:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "223brm9a1b2c"
down_revision: Union[str, Sequence[str], None] = "222crs8f4c5d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_column_if_missing(insp, table: str, column: str) -> None:
    if table not in insp.get_table_names():
        # Fresh DB: the baseline revision's create_all already built the table at
        # its current shape (with the new column). Nothing to backfill.
        return
    existing = {c["name"] for c in insp.get_columns(table)}
    if column not in existing:
        op.add_column(table, sa.Column(column, sa.String(), nullable=True))


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
    _add_column_if_missing(insp, "products", "brand")
    _add_column_if_missing(insp, "products", "manufacturer")


def downgrade() -> None:
    insp = inspect(op.get_bind())
    _drop_column_if_present(insp, "products", "manufacturer")
    _drop_column_if_present(insp, "products", "brand")
