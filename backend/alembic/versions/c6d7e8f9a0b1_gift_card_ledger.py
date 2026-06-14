"""F-038 follow-up: add gift_card_ledger (audit rows for non-sale balance moves).

Records the management movements a gift card undergoes off the sale path —
``reload`` (top-up), ``refund`` (a sale refunded back onto the card), and ``void``
(cancellation) — each row pinning the amount and the resulting ``balance_after``.
Redemptions are already recorded as ``giftcard`` tenders on the sale, so they are not
duplicated here. See ISSUE-057.

Revision ID: c6d7e8f9a0b1
Revises: b0c1d2e3f4a5
Create Date: 2026-06-14 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "c6d7e8f9a0b1"
down_revision: Union[str, Sequence[str], None] = "b0c1d2e3f4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if "gift_card_ledger" in insp.get_table_names():
        # Fresh DB: the baseline create_all already built it at its current shape.
        return
    op.create_table(
        "gift_card_ledger",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=False),
        sa.Column("gift_card_id", sa.Integer(), nullable=False),
        sa.Column("entry_type", sa.String(), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False, server_default="0"),
        sa.Column("balance_after", sa.Float(), nullable=False),
        sa.Column("transaction_id", sa.Integer(), nullable=True),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_gift_card_ledger_user_id", "gift_card_ledger", ["user_id"])
    op.create_index("ix_gift_card_ledger_client_id", "gift_card_ledger", ["client_id"])
    op.create_index("ix_gift_card_ledger_gift_card_id", "gift_card_ledger", ["gift_card_id"])
    op.create_index(
        "ix_gift_card_ledger_transaction_id", "gift_card_ledger", ["transaction_id"]
    )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if "gift_card_ledger" in insp.get_table_names():
        op.drop_table("gift_card_ledger")
