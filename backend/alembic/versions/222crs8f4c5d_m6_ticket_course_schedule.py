"""M6·Restaurant / issue-222: order-ticket course scheduling (coursing).

Adds ``order_tickets.course_schedule`` — a serialized JSON map of
``course -> ISO fire time`` set by the "schedule course" flow and drained by the
"fire due courses" sweep (M6). A server paces a multi-course meal by scheduling
when each course fires instead of firing every course by hand.

On a fresh database the baseline revision's ``create_all`` already builds the
column at its current shape, so the add is guarded idempotently — it only acts on
a database migrated to head before this revision existed.

Revision ID: 222crs8f4c5d
Revises: 222drv7e2a3b
Create Date: 2026-06-30 23:55:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "222crs8f4c5d"
down_revision: Union[str, Sequence[str], None] = "222drv7e2a3b"
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
        insp,
        "order_tickets",
        sa.Column(
            "course_schedule", sa.String(), nullable=True, server_default="{}"
        ),
    )


def downgrade() -> None:
    insp = inspect(op.get_bind())
    _drop_column_if_present(insp, "order_tickets", "course_schedule")
