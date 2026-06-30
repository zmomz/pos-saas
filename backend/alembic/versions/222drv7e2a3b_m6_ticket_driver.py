"""M6·Restaurant / issue-222: order-ticket delivery-driver assignment.

Adds ``order_tickets.driver_id`` + ``order_tickets.driver_name`` — the staff
member carrying a delivery order, set by the "assign driver" flow (F-045).
``driver_id`` references the owner's own ``staff_members`` row; ``driver_name``
snapshots the name so dispatch renders who has the bag without a join.

On a fresh database the baseline revision's ``create_all`` already builds the
columns at their current shape, so the adds are guarded idempotently — they only
act on a database migrated to head before this revision existed.

Revision ID: 222drv7e2a3b
Revises: 222hph6d0e1f
Create Date: 2026-06-30 23:40:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "222drv7e2a3b"
down_revision: Union[str, Sequence[str], None] = "222hph6d0e1f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_column_if_missing(insp, table: str, column: sa.Column) -> None:
    if table not in insp.get_table_names():
        # Fresh DB: create_all already built the table at its current shape.
        return
    existing = {c["name"] for c in insp.get_columns(table)}
    if column.name not in existing:
        op.add_column(table, column)


def _drop_column_if_present(insp, table: str, column: str) -> None:
    if table in insp.get_table_names():
        existing = {c["name"] for c in insp.get_columns(table)}
        if column in existing:
            op.drop_column(table, column)


def upgrade() -> None:
    insp = inspect(op.get_bind())
    _add_column_if_missing(
        insp, "order_tickets", sa.Column("driver_id", sa.Integer(), nullable=True)
    )
    _add_column_if_missing(
        insp, "order_tickets", sa.Column("driver_name", sa.String(), nullable=True)
    )


def downgrade() -> None:
    insp = inspect(op.get_bind())
    _drop_column_if_present(insp, "order_tickets", "driver_name")
    _drop_column_if_present(insp, "order_tickets", "driver_id")
