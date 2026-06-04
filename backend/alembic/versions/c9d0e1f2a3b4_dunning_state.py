"""F-028 / CL-06: subscription dunning state machine.

Adds ``clients.dunning_attempts`` (consecutive failed-charge counter) and
``clients.grace_deadline`` (ISO date by which the merchant must pay before the
next retry escalates / suspends). They drive the active -> past_due -> dunning
-> suspended walk in ``services/dunning.py`` and the client-facing PRN-09 notice.

On a fresh database the baseline revision's ``create_all`` already builds the
``clients`` table at its current shape (with the new columns), so each add is
guarded idempotently — it only acts on a database migrated to head before this
revision existed. See finding F-028.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-06-04 12:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, Sequence[str], None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_column_if_missing(insp, table: str, column: sa.Column) -> None:
    if table not in insp.get_table_names():
        # Fresh DB: the baseline revision's create_all already built the table at
        # its current shape (with the new column). Nothing to backfill.
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
        "clients",
        sa.Column("dunning_attempts", sa.Integer(), nullable=True, server_default="0"),
    )
    _add_column_if_missing(
        insp,
        "clients",
        sa.Column("grace_deadline", sa.String(), nullable=True),
    )


def downgrade() -> None:
    insp = inspect(op.get_bind())
    _drop_column_if_present(insp, "clients", "grace_deadline")
    _drop_column_if_present(insp, "clients", "dunning_attempts")
