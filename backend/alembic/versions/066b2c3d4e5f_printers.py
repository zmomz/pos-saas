"""ISSUE-047 (H26/U5.2): saved-printer registry + per-station routing.

Adds the ``printers`` table — one row per printer a merchant registers, carrying
its ``role`` (receipt/kot), an optional ``station_id`` (KOT → prep station), an
``is_default`` selection flag, and an opaque client-side ``device_id``. The
routing resolver (``services.printers.resolve_printer``) reads it to decide which
printer a printable streams to.

On a fresh database the baseline ``create_all`` already builds the table at its
current shape, so the create is guarded to be idempotent — it only builds the
table on a database migrated to head before this revision existed.

Revision ID: 066b2c3d4e5f
Revises: 065a1b2c3d4e
Create Date: 2026-06-14 16:45:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "066b2c3d4e5f"
down_revision: Union[str, Sequence[str], None] = "065a1b2c3d4e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if "printers" in insp.get_table_names():
        return
    op.create_table(
        "printers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False, server_default="receipt"),
        sa.Column("station_id", sa.Integer(), nullable=True),
        sa.Column("device_id", sa.String(), nullable=True),
        sa.Column("paper_size", sa.String(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_printers_user_id", "printers", ["user_id"])
    op.create_index("ix_printers_client_id", "printers", ["client_id"])
    op.create_index("ix_printers_station_id", "printers", ["station_id"])


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if "printers" in insp.get_table_names():
        op.drop_table("printers")
