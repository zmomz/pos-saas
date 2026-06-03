"""PAY-01/05/09: add payment_tenders (captured tenders, no PAN).

Introduces the ``payment_tenders`` table so a card/Mada/wallet/BNPL tender on a
sale records a **real captured approval** (network + approval_code + rrn +
gateway_ref) instead of just a method label, and so PCI scope stays minimized —
only a gateway token + last 4 digits are stored, never a PAN. The decline path
rolls the sale back, so a declined tender is normally never persisted. See
findings F-001 (capture), F-002 (Saudi tenders), F-003 (this model).

Revision ID: a1b2c3d4e5f6
Revises: f5a6b7c8d9e0
Create Date: 2026-06-03 14:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "f5a6b7c8d9e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if "payment_tenders" in insp.get_table_names():
        # Fresh DB: the baseline create_all already built it at its current shape.
        return
    op.create_table(
        "payment_tenders",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=False),
        sa.Column("transaction_id", sa.Integer(), nullable=True),
        sa.Column("tender_type", sa.String(), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("network", sa.String(), nullable=True),
        sa.Column("approval_code", sa.String(), nullable=True),
        sa.Column("rrn", sa.String(), nullable=True),
        sa.Column("gateway_ref", sa.String(), nullable=True),
        sa.Column("last4", sa.String(), nullable=True),
        sa.Column("token", sa.String(), nullable=True),
        sa.Column("gateway", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="captured"),
        sa.Column("decline_reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_payment_tenders_user_id", "payment_tenders", ["user_id"])
    op.create_index("ix_payment_tenders_client_id", "payment_tenders", ["client_id"])
    op.create_index("ix_payment_tenders_transaction_id", "payment_tenders", ["transaction_id"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if "payment_tenders" in insp.get_table_names():
        op.drop_table("payment_tenders")
