"""ISSUE-081: optional MFA (TOTP) — user_mfa table.

Adds the ``user_mfa`` table holding per-user TOTP state: the base32 ``secret``,
an ``enabled`` flag (only true once a code has been verified), and the JSON
``recovery_codes`` (single-use backup codes stored as bcrypt hashes).

On a fresh database the baseline ``create_all`` already builds the table at its
current shape, so the create is guarded to be idempotent — it only acts on a
database migrated to head before this revision existed.

Revision ID: 4d5e6f708192
Revises: 3c4d5e6f7081
Create Date: 2026-06-15 02:05:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "4d5e6f708192"
down_revision: Union[str, Sequence[str], None] = "3c4d5e6f7081"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if "user_mfa" in insp.get_table_names():
        return
    op.create_table(
        "user_mfa",
        sa.Column("user_id", sa.String(length=255), primary_key=True),
        sa.Column("secret", sa.String(length=64), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("recovery_codes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_user_mfa_user_id", "user_mfa", ["user_id"])


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if "user_mfa" not in insp.get_table_names():
        return
    op.drop_index("ix_user_mfa_user_id", table_name="user_mfa")
    op.drop_table("user_mfa")
