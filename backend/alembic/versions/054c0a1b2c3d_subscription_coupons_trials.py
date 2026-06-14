"""ISSUE-054: subscription coupons & trials — add coupon/trial columns to clients.

Adds four nullable columns to ``clients``:
- ``coupon_type`` / ``coupon_value`` — the discount applied to the subscription
  fee ('percentage' | 'fixed', and the amount off).
- ``coupon_duration_remaining`` — how many billing periods the coupon still
  applies to; decremented on each discounted charge and cleared when spent.
- ``trial_end`` — ISO date; while in the future the first charge is deferred.

On a fresh database the baseline revision's ``create_all`` already builds the
table at its current shape (with the columns), so each add is guarded to be
idempotent — it only backfills a database migrated to head before this revision
existed.

Revision ID: 054c0a1b2c3d
Revises: b1c2d3e4f5a6
Create Date: 2026-06-14 05:05:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "054c0a1b2c3d"
down_revision: Union[str, Sequence[str], None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "clients"
_COLUMNS = (
    ("coupon_type", sa.String(), None),
    ("coupon_value", sa.Float(), None),
    ("coupon_duration_remaining", sa.Integer(), "0"),
    ("trial_end", sa.String(), None),
)


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if _TABLE not in insp.get_table_names():
        # Fresh DB: create_all already built the table with these columns.
        return
    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    for name, type_, server_default in _COLUMNS:
        if name not in existing:
            op.add_column(
                _TABLE,
                sa.Column(name, type_, nullable=True, server_default=server_default),
            )


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if _TABLE not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    for name, _type, _sd in reversed(_COLUMNS):
        if name in existing:
            op.drop_column(_TABLE, name)
