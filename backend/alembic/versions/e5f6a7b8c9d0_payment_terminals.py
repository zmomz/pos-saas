"""F-005 / HW-03 / PAY-05: integrated payment terminals (paired SoftPOS devices).

Adds the ``terminals`` table the payments family was missing (deferred from F-003):
a merchant registers the in-store SoftPOS terminal(s) they have paired (Geidea), so
a card-like tender at checkout can be pushed to a specific device for a real
approval.

On a fresh database the baseline revision's ``create_all`` already builds this table
at its current shape, so the create is guarded to be idempotent — it only acts on a
database that was migrated to head before this revision existed. See finding F-005.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-03 18:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if "terminals" not in insp.get_table_names():
        op.create_table(
            "terminals",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("client_id", sa.Integer(), nullable=True),
            sa.Column("branch_id", sa.Integer(), nullable=True),
            sa.Column("provider", sa.String(), nullable=False, server_default="geidea"),
            sa.Column("label", sa.String(), nullable=True),
            sa.Column("serial", sa.String(), nullable=True),
            sa.Column("status", sa.String(), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_terminals_user_id", "terminals", ["user_id"])
        op.create_index("ix_terminals_client_id", "terminals", ["client_id"])


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if "terminals" in insp.get_table_names():
        op.drop_table("terminals")
