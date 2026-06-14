"""ISSUE-079: per-merchant store settings (store_settings).

Adds the ``store_settings`` table holding the merchant-level fields that feed the
store-settings screen but are NOT already on the ``clients`` row: the Commercial
Registration (CR) number, the receipt footer line, the branch profile
(address / city / phone) and the business hours (a JSON string). The seller name
and VAT number stay on ``clients`` (written through from the screen).

On a fresh database the baseline revision's ``create_all`` already builds the
table at its current shape, so the create is guarded to be idempotent — it only
acts on a database migrated to head before this revision existed.

Revision ID: 3c4d5e6f7081
Revises: 2b3c4d5e6f70
Create Date: 2026-06-15 01:05:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "3c4d5e6f7081"
down_revision: Union[str, Sequence[str], None] = "2b3c4d5e6f70"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if "store_settings" in insp.get_table_names():
        return
    op.create_table(
        "store_settings",
        sa.Column("owner_user_id", sa.String(), primary_key=True),
        sa.Column("cr_number", sa.String(), nullable=True),
        sa.Column("receipt_footer", sa.String(), nullable=True),
        sa.Column("address", sa.String(), nullable=True),
        sa.Column("city", sa.String(), nullable=True),
        sa.Column("phone", sa.String(), nullable=True),
        sa.Column("business_hours", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_store_settings_owner_user_id", "store_settings", ["owner_user_id"])


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if "store_settings" not in insp.get_table_names():
        return
    op.drop_index("ix_store_settings_owner_user_id", table_name="store_settings")
    op.drop_table("store_settings")
