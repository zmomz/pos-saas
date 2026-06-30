"""#206: subscription lifecycle — add pause/cancel stamps to clients.

The self-serve subscription lifecycle (#206) adds two merchant-managed states to
``clients.subscription_status`` — ``'paused'`` and ``'cancelled'`` — which are
plain string values and need no schema change. It does add two ISO-date stamp
columns so the lifecycle is reversible and auditable:

- ``subscription_paused_at`` — the date the merchant paused on; resume shifts
  ``next_billing_date`` forward by the paused span so paid days are preserved.
- ``subscription_cancelled_at`` — the date the merchant cancelled on; surfaced in
  the billing UI.

On a fresh database the baseline ``create_all`` already builds ``clients`` with
the columns, so each add is guarded to be idempotent — it only backfills a
database migrated to head before this revision existed.

Revision ID: a1b2c3d4e5f6
Revises: c4e5f6a7b8d9
Create Date: 2026-06-29 12:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "c4e5f6a7b8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "clients"
_COLUMNS = ("subscription_paused_at", "subscription_cancelled_at")


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if _TABLE not in insp.get_table_names():
        # Fresh DB: create_all already built the table with these columns.
        return
    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    for name in _COLUMNS:
        if name not in existing:
            op.add_column(_TABLE, sa.Column(name, sa.String(), nullable=True))


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if _TABLE not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    for name in reversed(_COLUMNS):
        if name in existing:
            op.drop_column(_TABLE, name)
