"""REV-02: add ``channel_orders.ticket_id`` so stuck aggregator claims can recover.

DAT-07 made the aggregator ingest (F-060) claim the order (``status="received"``,
committed) before any fiscal work. The gap REV-02 closes: a crash — or a transient
``execute_sale`` failure — after the claim commit but before any invoice is minted
left the claim stranded at ``received`` / ``transaction_id IS NULL`` with no recovery
path, so a re-delivery returned ``duplicate`` and the sale was never invoiced.

The fix records the materialized order ticket on the claim **before** the settle, so
a re-delivery of a stuck claim re-uses that ticket — re-settling it when it never
settled, or detecting it already ``settled`` (the crash-AFTER-settle case) so it
never mints a second invoice.

On a fresh database the model metadata already builds ``channel_orders`` with the
column (``create_all``), so the add is guarded to be idempotent.

Revision ID: fc2d3e4a5b6c
Revises: f1a2b3c4d5e6
Create Date: 2026-06-27 16:40:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "fc2d3e4a5b6c"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "channel_orders"
_COLUMN = "ticket_id"


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if _TABLE not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    if _COLUMN not in existing:
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.Integer(), nullable=True))
        op.create_index(f"ix_{_TABLE}_{_COLUMN}", _TABLE, [_COLUMN])


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if _TABLE not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    if _COLUMN in existing:
        try:
            op.drop_index(f"ix_{_TABLE}_{_COLUMN}", table_name=_TABLE)
        except Exception:
            pass
        op.drop_column(_TABLE, _COLUMN)
