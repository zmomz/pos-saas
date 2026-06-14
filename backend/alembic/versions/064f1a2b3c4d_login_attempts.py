"""ISSUE-043: login brute-force attempt tracker.

Adds ``login_attempts`` — one row per (identifier, IP) recording failed-login
counts and the active lockout window used by ``services.login_throttle`` to
throttle credential-stuffing against ``POST /api/v1/auth/login``.

On a fresh database the baseline ``create_all`` already builds the table at its
current shape, so the create is guarded to be idempotent — it only backfills a
database migrated to head before this revision existed.

Revision ID: 064f1a2b3c4d
Revises: 063e0f1a2b3c
Create Date: 2026-06-14 16:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "064f1a2b3c4d"
down_revision: Union[str, Sequence[str], None] = "063e0f1a2b3c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "login_attempts"


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if _TABLE in insp.get_table_names():
        # Fresh DB: create_all already built the table at the current shape.
        return
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("identifier", sa.String(), nullable=False),
        sa.Column("ip_address", sa.String(), nullable=False, server_default="unknown"),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("first_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("identifier", "ip_address", name="uq_login_attempts_identifier_ip"),
    )
    op.create_index(f"ix_{_TABLE}_identifier", _TABLE, ["identifier"])
    op.create_index(f"ix_{_TABLE}_id", _TABLE, ["id"])


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if _TABLE not in insp.get_table_names():
        return
    op.drop_table(_TABLE)
