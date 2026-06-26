"""FIN-03: convert gift_cards balance columns from FLOAT to Numeric(12,2).

Gift-card money now runs through ``core.money`` (Decimal, half-up). The stored
balance has to back that: ``gift_cards.initial_balance`` and ``gift_cards.balance``
were ``FLOAT`` and so inherited binary-float subtraction drift
(``0.30 - 0.10 == 0.19999…``), which could leave a card's remaining balance just
shy of a penny it should still hold. This converts both to ``Numeric(12,2)`` so
the DDL matches the ORM ``Money`` type and balances stay penny-exact.

SQLite cannot ``ALTER COLUMN`` a type in place, so each change goes through a
batch (table-rebuild) operation; existing FLOAT values copy across unchanged. On
a fresh database the baseline ``create_all`` already builds the columns as
``Numeric(12,2)`` from the model, so the conversion is a no-op rebuild there.

Revision ID: a1c2e3d4f5b6
Revises: fb1c2d3e4a5b
Create Date: 2026-06-26 18:50:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1c2e3d4f5b6"
down_revision: Union[str, Sequence[str], None] = "fb1c2d3e4a5b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = ("initial_balance", "balance")


def upgrade() -> None:
    with op.batch_alter_table("gift_cards") as batch:
        for column in _COLUMNS:
            batch.alter_column(
                column,
                existing_type=sa.Float(),
                type_=sa.Numeric(precision=12, scale=2),
                existing_nullable=False,
            )


def downgrade() -> None:
    with op.batch_alter_table("gift_cards") as batch:
        for column in _COLUMNS:
            batch.alter_column(
                column,
                existing_type=sa.Numeric(precision=12, scale=2),
                type_=sa.Float(),
                existing_nullable=False,
            )
