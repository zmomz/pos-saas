"""ISSUE-038 (H7): product↔category linkage — add products.category_id.

Adds ``products.category_id``, the FK linking a product to a row in the merchant's
``categories`` tree. The legacy free-text ``products.category`` is retained
(denormalised name) for display continuity; ``category_id`` is the real owner-scoped
link that lists/filters resolve against.

Stored as a nullable integer so existing products are unaffected (they remain
uncategorised until edited). On a fresh database the baseline revision's
``create_all`` already builds ``products`` at its current shape (with the column),
so the add is guarded to be idempotent — it only backfills a database migrated to
head before this revision existed.

Revision ID: 065a1b2c3d4e
Revises: 064f1a2b3c4d
Create Date: 2026-06-14 16:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "065a1b2c3d4e"
down_revision: Union[str, Sequence[str], None] = "064f1a2b3c4d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_column_if_missing(insp, table: str, column: str) -> None:
    if table not in insp.get_table_names():
        # Fresh DB: the baseline revision's create_all already built the table at
        # its current shape (with the new column). Nothing to backfill.
        return
    existing = {c["name"] for c in insp.get_columns(table)}
    if column not in existing:
        op.add_column(table, sa.Column(column, sa.Integer(), nullable=True))


def _drop_column_if_present(insp, table: str, column: str) -> None:
    if table in insp.get_table_names():
        existing = {c["name"] for c in insp.get_columns(table)}
        if column in existing:
            op.drop_column(table, column)


def upgrade() -> None:
    insp = inspect(op.get_bind())
    _add_column_if_missing(insp, "products", "category_id")


def downgrade() -> None:
    insp = inspect(op.get_bind())
    _drop_column_if_present(insp, "products", "category_id")
