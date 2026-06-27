"""REV-05: add ``channel_orders.settling_at`` for the aggregator settle lock.

REV-02 (#175) gave the aggregator ingest a *resume* path: a re-delivery of a claim
still at ``received`` with no transaction re-runs settlement. It had no mutual
exclusion, so two concurrent re-deliveries both settled — minting two ZATCA invoices
and two KDS tickets for one order (#179).

The fix makes the settler win an atomic ``received -> settling`` compare-and-set
before any fiscal work; a loser backs off as a duplicate. A claim whose settler
crashed mid-flight is stranded at ``settling`` forever, so the recovery is a
**bounded sweep** that re-opens claims stuck in ``settling`` past a threshold — keyed
on this ``settling_at`` timestamp (when the lock was taken).

On a fresh database the model metadata already builds ``channel_orders`` with the
column (``create_all``), so the add is guarded to be idempotent.

Revision ID: c4e5f6a7b8d9
Revises: b3d4e5f6a7c8
Create Date: 2026-06-27 18:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "c4e5f6a7b8d9"
down_revision: Union[str, Sequence[str], None] = "b3d4e5f6a7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "channel_orders"
_COLUMN = "settling_at"


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if _TABLE not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    if _COLUMN not in existing:
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if _TABLE not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    if _COLUMN in existing:
        op.drop_column(_TABLE, _COLUMN)
