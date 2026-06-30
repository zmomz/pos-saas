"""ISSUE-223 (M4 Product): serial/IMEI tracking — add products.track_serial.

Adds an optional ``track_serial`` boolean flag: a serialised good (a phone/IMEI,
appliance or any warranty-tracked item) whose individual unit must be identified
at the point of sale. When set, the POS sale path rejects a line for this product
that arrives without a serial number. NULL (legacy rows) is treated as untracked.

On a fresh database the baseline revision's ``create_all`` already builds the
``products`` table at its current shape (with the new column), so the add is
guarded to be idempotent — it only acts on a database migrated to head before
this revision existed. Mirrors the digital-product revision (223dig0a1b2c).

Revision ID: 223ser0a1b2c
Revises: 223dig0a1b2c
Create Date: 2026-06-30 23:35:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "223ser0a1b2c"
down_revision: Union[str, Sequence[str], None] = "223dig0a1b2c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_column_if_missing(insp, table: str, column: str) -> None:
    if table not in insp.get_table_names():
        # Fresh DB: the baseline revision's create_all already built the table at
        # its current shape (with the new column). Nothing to backfill.
        return
    existing = {c["name"] for c in insp.get_columns(table)}
    if column not in existing:
        op.add_column(
            table,
            sa.Column(
                column,
                sa.Boolean(),
                nullable=True,
                server_default=sa.text("false"),
            ),
        )


def _drop_column_if_present(insp, table: str, column: str) -> None:
    if table in insp.get_table_names():
        existing = {c["name"] for c in insp.get_columns(table)}
        if column in existing:
            op.drop_column(table, column)


def upgrade() -> None:
    insp = inspect(op.get_bind())
    _add_column_if_missing(insp, "products", "track_serial")


def downgrade() -> None:
    insp = inspect(op.get_bind())
    _drop_column_if_present(insp, "products", "track_serial")
