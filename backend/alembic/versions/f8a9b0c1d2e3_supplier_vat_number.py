"""ISSUE-063: supplier VAT number — add suppliers.vat_number.

Adds ``suppliers.vat_number``, the supplier's Saudi VAT registration number (TRN)
captured for compliance/reporting. It is a 15-digit code (validated at the API
layer), stored as a nullable string so existing suppliers are unaffected.

On a fresh database the baseline revision's ``create_all`` already builds the
``suppliers`` table at its current shape (with the column), so the add is guarded
to be idempotent — it only backfills a database migrated to head before this
revision existed.

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-06-14 01:30:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "f8a9b0c1d2e3"
down_revision: Union[str, Sequence[str], None] = "e7f8a9b0c1d2"
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
            op.drop_column(table, column)


def upgrade() -> None:
    insp = inspect(op.get_bind())
    _add_column_if_missing(insp, "suppliers", "vat_number")


def downgrade() -> None:
    insp = inspect(op.get_bind())
    _drop_column_if_present(insp, "suppliers", "vat_number")
