"""Phase D: quotations

Adds the ``quotations`` table — a non-fiscal pre-sale price-quotation document
(عرض سعر) that mirrors a transaction's shape but is not a ZATCA tax invoice.

(The agent ``default_language`` column used by L10N-05 already exists from the
earlier ``368d6a17ebd5`` revision, so no agents change is needed here.)

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-06-02 16:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, Sequence[str], None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "quotations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=True),
        sa.Column("quote_number", sa.String(), nullable=True),
        sa.Column("customer_name", sa.String(), nullable=True),
        sa.Column("customer_phone", sa.String(), nullable=True),
        sa.Column("items_json", sa.String(), nullable=True),
        sa.Column("subtotal", sa.Float(), server_default="0", nullable=True),
        sa.Column("vat_amount", sa.Float(), server_default="0", nullable=True),
        sa.Column("discount_amount", sa.Float(), server_default="0", nullable=True),
        sa.Column("total_amount", sa.Float(), server_default="0", nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(), server_default="draft", nullable=True),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_quotations_id"), "quotations", ["id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("quotations")
