"""ISSUE-065 (P2 catalog): product images — add products.image_url.

Adds the served URL of a product's image (catalog + POS tile grid). The file is
stored under ``uploads/products/`` and served from ``/uploads``; NULL means the
product has no image (the tile falls back to its name initial).

On a fresh database the baseline revision's ``create_all`` already builds the
``products`` table at its current shape (with the new column), so the add is
guarded to be idempotent — it only acts on a database migrated to head before
this revision existed. Mirrors the reorder_point revision (c4d5e6f7a8b9).

Revision ID: 069e5f6a7b8c
Revises: 068d4e5f6a7b
Create Date: 2026-06-14 12:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "069e5f6a7b8c"
down_revision: Union[str, Sequence[str], None] = "068d4e5f6a7b"
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
    _add_column_if_missing(insp, "products", "image_url")


def downgrade() -> None:
    insp = inspect(op.get_bind())
    _drop_column_if_present(insp, "products", "image_url")
