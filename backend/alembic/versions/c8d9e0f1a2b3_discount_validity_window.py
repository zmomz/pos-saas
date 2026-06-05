"""F-041 / PRC-02: scheduled validity window on discount/promo codes.

Adds ``starts_at`` / ``ends_at`` to ``discounts`` so a coupon can be a time-window
promotion — only honoured between the two bounds (either NULL ⇒ open-ended on that
side). The server-side validator (``DiscountsService.validate``) enforces the window
on both the ``/validate`` preview and the atomic sale path, so a code outside its
window is rejected before any sale is written.

On a fresh database the baseline revision's ``create_all`` already builds ``discounts``
with these columns, so the add is guarded to be idempotent — it only acts on a database
that was migrated to head before this revision existed. See finding F-041.

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-06-05 13:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "c8d9e0f1a2b3"
down_revision: Union[str, Sequence[str], None] = "b7c8d9e0f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(insp) -> set:
    if "discounts" not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns("discounts")}


def upgrade() -> None:
    insp = inspect(op.get_bind())
    existing = _columns(insp)
    if "discounts" not in insp.get_table_names():
        return
    if "starts_at" not in existing:
        op.add_column(
            "discounts",
            sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "ends_at" not in existing:
        op.add_column(
            "discounts",
            sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    insp = inspect(op.get_bind())
    existing = _columns(insp)
    if "ends_at" in existing:
        op.drop_column("discounts", "ends_at")
    if "starts_at" in existing:
        op.drop_column("discounts", "starts_at")
