"""CRM-03/PRC-05: add gift_cards (prepaid store credit redeemable as a tender).

Introduces the ``gift_cards`` table so a merchant can issue prepaid store credit
that is later redeemed as a sale *tender* (PRC-05), its balance decremented
atomically inside the sale transaction. The bearer ``code`` is generated
server-side; the table stores the live ``balance``, the issued ``initial_balance``,
a status, and an optional expiry. See finding F-038.

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-06-05 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "c5d6e7f8a9b0"
down_revision: Union[str, Sequence[str], None] = "b4c5d6e7f8a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if "gift_cards" in insp.get_table_names():
        # Fresh DB: the baseline create_all already built it at its current shape.
        return
    op.create_table(
        "gift_cards",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("currency", sa.String(), nullable=False, server_default="SAR"),
        sa.Column("initial_balance", sa.Float(), nullable=False),
        sa.Column("balance", sa.Float(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("expiry_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_gift_cards_user_id", "gift_cards", ["user_id"])
    op.create_index("ix_gift_cards_client_id", "gift_cards", ["client_id"])
    op.create_index("ix_gift_cards_code", "gift_cards", ["code"])
    op.create_index("ix_gift_cards_customer_id", "gift_cards", ["customer_id"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if "gift_cards" in insp.get_table_names():
        op.drop_table("gift_cards")
