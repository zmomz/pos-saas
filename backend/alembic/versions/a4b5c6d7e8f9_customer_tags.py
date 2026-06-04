"""CRM-04 (F-039): add customers.tags for segmentation.

Adds a single ``tags`` TEXT column to ``customers`` holding a JSON-encoded list
of free-form segment labels (e.g. ``["vip", "wholesale"]``). Kept as one column
(no join table) so it rides the generic customers triad; the router serializes
the list in and parses it back out. Pairs with the computed RFM/LTV insights
endpoint (``GET /api/v1/entities/customers/{id}/insights``) — neither needs a
schema change beyond this label column. See finding F-039.

Revision ID: a4b5c6d7e8f9
Revises: c5d6e7f8a9b0
Create Date: 2026-06-05 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "a4b5c6d7e8f9"
down_revision: Union[str, Sequence[str], None] = "c5d6e7f8a9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    cols = {c["name"] for c in insp.get_columns("customers")}
    if "tags" in cols:
        # Fresh DB: the baseline create_all already built the column at its
        # current shape — nothing to do (idempotent, mirrors the sibling
        # migrations' inspect-guard).
        return
    op.add_column("customers", sa.Column("tags", sa.String(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    cols = {c["name"] for c in insp.get_columns("customers")}
    if "tags" not in cols:
        return
    with op.batch_alter_table("customers") as batch:
        batch.drop_column("tags")
