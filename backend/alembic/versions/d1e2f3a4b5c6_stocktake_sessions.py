"""M4 / #207: guided stocktake — sessioned count tables.

Adds ``stock_count_sessions`` (the resumable stocktake header) and
``stock_count_lines`` (one snapshotted line per product) backing the guided
start → freeze → count → variance → approve flow. Approval posts ``stock_adjustments``
rows (INV-06) atomically; these tables are the convenience/session layer on top.

On a fresh database the baseline revision's ``create_all`` already builds these
tables at their current shape (the router imports the models at startup), so the
creates are guarded to be idempotent — they only act on a database migrated to head
before this revision existed.

Revision ID: d1e2f3a4b5c6
Revises: c4e5f6a7b8d9
Create Date: 2026-06-29 12:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, Sequence[str], None] = "c4e5f6a7b8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = inspect(op.get_bind())

    if "stock_count_sessions" not in insp.get_table_names():
        op.create_table(
            "stock_count_sessions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("client_id", sa.Integer(), nullable=True),
            sa.Column("branch_id", sa.Integer(), nullable=True),
            sa.Column("name", sa.String(), nullable=True),
            sa.Column("status", sa.String(), nullable=False, server_default="draft"),
            sa.Column("note", sa.String(), nullable=True),
            sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index(
            "ix_stock_count_sessions_user_id", "stock_count_sessions", ["user_id"]
        )
        op.create_index(
            "ix_stock_count_sessions_client_id", "stock_count_sessions", ["client_id"]
        )

    if "stock_count_lines" not in insp.get_table_names():
        op.create_table(
            "stock_count_lines",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("session_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("client_id", sa.Integer(), nullable=True),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("product_name", sa.String(), nullable=True),
            sa.Column("system_quantity", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("counted_quantity", sa.Integer(), nullable=True),
            sa.Column("variance", sa.Integer(), nullable=True),
            sa.Column("note", sa.String(), nullable=True),
            sa.Column("counted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index(
            "ix_stock_count_lines_session_id", "stock_count_lines", ["session_id"]
        )
        op.create_index(
            "ix_stock_count_lines_user_id", "stock_count_lines", ["user_id"]
        )


def downgrade() -> None:
    insp = inspect(op.get_bind())

    if "stock_count_lines" in insp.get_table_names():
        op.drop_index("ix_stock_count_lines_user_id", table_name="stock_count_lines")
        op.drop_index("ix_stock_count_lines_session_id", table_name="stock_count_lines")
        op.drop_table("stock_count_lines")

    if "stock_count_sessions" in insp.get_table_names():
        op.drop_index("ix_stock_count_sessions_client_id", table_name="stock_count_sessions")
        op.drop_index("ix_stock_count_sessions_user_id", table_name="stock_count_sessions")
        op.drop_table("stock_count_sessions")
