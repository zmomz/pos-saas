"""ISSUE-059: single-use / unique discount codes — add ``discount_codes`` table.

Adds the ``discount_codes`` table backing batch-minted, single-use codes (distinct
from the reusable ``discounts`` definitions): each row is one unique ``code`` in a
``batch_id`` group, redeemable exactly once (``redeemed``/``redeemed_at``) within an
optional validity window (``starts_at``/``ends_at``).

On a fresh database the baseline revision's ``create_all`` already builds the table
at its current shape, so the create is guarded to be idempotent — it only backfills
a database migrated to head before this revision existed.

Revision ID: a9b0c1d2e3f4
Revises: f8a9b0c1d2e3
Create Date: 2026-06-14 01:55:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "a9b0c1d2e3f4"
down_revision: Union[str, Sequence[str], None] = "f8a9b0c1d2e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if "discount_codes" in insp.get_table_names():
        # Fresh DB: the baseline create_all already built the table at its current
        # shape. Nothing to backfill.
        return
    op.create_table(
        "discount_codes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("batch_id", sa.String(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("min_purchase", sa.Float(), nullable=True),
        sa.Column("redeemed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_discount_codes_user_id", "discount_codes", ["user_id"])
    op.create_index("ix_discount_codes_batch_id", "discount_codes", ["batch_id"])
    op.create_index("ix_discount_codes_code", "discount_codes", ["code"])


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if "discount_codes" in insp.get_table_names():
        op.drop_table("discount_codes")
