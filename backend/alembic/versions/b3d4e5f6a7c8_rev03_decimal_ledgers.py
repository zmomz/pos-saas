"""REV-03: convert secondary-ledger money columns from FLOAT to Numeric(12,2).

FIN-01/03 converted the billing and gift-card *balance* columns, but the POS
``transactions`` money columns and the ``gift_card_ledger`` audit rows still
stored money as ``FLOAT``. Their values are quantized on the way in (the app
math runs through ``core.money``), so this is not the original arbitrary-precision
bug — but the stored type should match the ORM ``Money`` type so the DDL is
consistent and the autogenerate diff is empty.

SQLite cannot ``ALTER COLUMN`` a type in place, so each change goes through a
batch (table-rebuild) operation; existing FLOAT values copy into the NUMERIC
column unchanged. On a fresh database the rebuild is harmless (the values are
already 2dp).

Revision ID: b3d4e5f6a7c8
Revises: fc2d3e4a5b6c
Create Date: 2026-06-27 17:10:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3d4e5f6a7c8"
down_revision: Union[str, Sequence[str], None] = "fc2d3e4a5b6c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (table, column, nullable) whose stored type moves FLOAT <-> Numeric(12, 2).
_COLUMNS = (
    ("transactions", "subtotal", True),
    ("transactions", "vat_amount", True),
    ("transactions", "discount_amount", True),
    ("transactions", "total_amount", False),
    ("transactions", "tip_amount", True),
    ("transactions", "cash_tendered", True),
    ("transactions", "change_due", True),
    ("gift_card_ledger", "amount", False),
    ("gift_card_ledger", "balance_after", False),
)


def upgrade() -> None:
    for table, column, nullable in _COLUMNS:
        with op.batch_alter_table(table) as batch:
            batch.alter_column(
                column,
                existing_type=sa.Float(),
                type_=sa.Numeric(precision=12, scale=2),
                existing_nullable=nullable,
            )


def downgrade() -> None:
    for table, column, nullable in _COLUMNS:
        with op.batch_alter_table(table) as batch:
            batch.alter_column(
                column,
                existing_type=sa.Numeric(precision=12, scale=2),
                type_=sa.Float(),
                existing_nullable=nullable,
            )
