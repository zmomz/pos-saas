"""FIN-01: convert the remaining billing money columns from FLOAT to Numeric(12,2).

All money math now runs through ``core.money`` (Decimal, half-up). The billing
domain's stored amounts back that: ``subscription_payments.amount`` and
``agent_quota_payments.amount`` were already ``NUMERIC(12,2)`` in the baseline,
but three columns lagged behind as ``FLOAT`` —
``clients.subscription_fee``, ``clients.coupon_value`` and ``agents.quota_price``.
This converts them to ``Numeric(12,2)`` so the DDL matches the ORM ``Money`` type
and the autogenerate diff is empty.

SQLite cannot ``ALTER COLUMN`` a type in place, so each change goes through a
batch (table-rebuild) operation; existing FLOAT values copy into the NUMERIC
column unchanged. On a fresh database the baseline ``create_all`` already builds
the columns as ``Numeric(12,2)`` from the model, so the conversion is a no-op
rebuild there.

Revision ID: fa1b2c3d4e5f
Revises: f9a0b1c2d3e4
Create Date: 2026-06-26 14:50:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fa1b2c3d4e5f"
down_revision: Union[str, Sequence[str], None] = "f9a0b1c2d3e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (table, column) pairs whose stored type moves FLOAT -> Numeric(12, 2).
_COLUMNS = (
    ("clients", "subscription_fee"),
    ("clients", "coupon_value"),
    ("agents", "quota_price"),
)


def upgrade() -> None:
    for table, column in _COLUMNS:
        with op.batch_alter_table(table) as batch:
            batch.alter_column(
                column,
                existing_type=sa.Float(),
                type_=sa.Numeric(precision=12, scale=2),
                existing_nullable=True,
            )


def downgrade() -> None:
    for table, column in _COLUMNS:
        with op.batch_alter_table(table) as batch:
            batch.alter_column(
                column,
                existing_type=sa.Numeric(precision=12, scale=2),
                type_=sa.Float(),
                existing_nullable=True,
            )
