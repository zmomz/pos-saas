"""M5·CRM / issue-221: customer groups & tiers.

Adds the ``customer_groups`` table (named segments with a tier label and an
optional default discount) and a ``customers.group_id`` column linking a customer
to at most one group.

On a fresh database the baseline revision's ``create_all`` already builds both at
their current shape, so every change is guarded idempotently — it only acts on a
database migrated to head before this revision existed.

Revision ID: b2c3d4e5f6a8
Revises: a1b2c3d4e5f7
Create Date: 2026-06-30 22:30:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a8"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f7"
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
    if "customer_groups" not in insp.get_table_names():
        op.create_table(
            "customer_groups",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("client_id", sa.Integer(), nullable=True),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("tier", sa.String(), nullable=True),
            sa.Column("discount_percent", sa.Float(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_customer_groups_user_id", "customer_groups", ["user_id"])
        op.create_index("ix_customer_groups_client_id", "customer_groups", ["client_id"])

    _add_column_if_missing(
        insp, "customers", sa.Column("group_id", sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    insp = inspect(op.get_bind())
    _drop_column_if_present(insp, "customers", "group_id")
    if "customer_groups" in insp.get_table_names():
        op.drop_table("customer_groups")
