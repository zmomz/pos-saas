"""F-033 / INV-04: product variants (matrix) — add the ``product_variants`` table.

A variant is a sellable SKU of a parent product with its own barcode, price and
stock (e.g. "Red / Large"). The POS resolves a scanned variant barcode to the
variant and decrements *its* stock independently of sibling variants.

On a fresh database the baseline revision's ``create_all`` already builds this
table at its current shape, so the create is guarded to be idempotent — it only
acts on a database migrated to head before this revision existed. See finding
F-033.

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-06-04 12:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, Sequence[str], None] = "d0e1f2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if "product_variants" not in insp.get_table_names():
        op.create_table(
            "product_variants",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("client_id", sa.Integer(), nullable=True),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("attributes", sa.String(), nullable=True),
            sa.Column("sku", sa.String(), nullable=True),
            sa.Column("barcode", sa.String(), nullable=True),
            sa.Column("price", sa.Float(), nullable=True),
            sa.Column("cost_price", sa.Float(), nullable=True),
            sa.Column("quantity", sa.Integer(), nullable=True, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=True, server_default="true"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_product_variants_user_id", "product_variants", ["user_id"])
        op.create_index("ix_product_variants_client_id", "product_variants", ["client_id"])
        op.create_index("ix_product_variants_product_id", "product_variants", ["product_id"])


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if "product_variants" in insp.get_table_names():
        op.drop_table("product_variants")
