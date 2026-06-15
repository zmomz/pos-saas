"""ISSUE-082: password reset — password_reset_tokens table + users.token_version.

Adds the ``password_reset_tokens`` table (single-use, time-limited reset grants;
only the SHA-256 hash of the token is stored) and a ``token_version`` security
stamp on ``users`` (every issued access/refresh token carries the value current
at mint time as its ``sv`` claim; a reset bumps it, dropping old sessions).

On a fresh database the baseline ``create_all`` already builds these at their
current shape, so each step is guarded to be idempotent — it only acts on a
database migrated to head before this revision existed.

Revision ID: 5e6f70819203
Revises: 4d5e6f708192
Create Date: 2026-06-15 02:45:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "5e6f70819203"
down_revision: Union[str, Sequence[str], None] = "4d5e6f708192"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = inspect(op.get_bind())

    if "password_reset_tokens" not in insp.get_table_names():
        op.create_table(
            "password_reset_tokens",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.String(length=255), nullable=False),
            sa.Column("token_hash", sa.String(length=64), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index(
            "ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"]
        )
        op.create_index(
            "ix_password_reset_tokens_token_hash",
            "password_reset_tokens",
            ["token_hash"],
            unique=True,
        )

    user_cols = {c["name"] for c in insp.get_columns("users")}
    if "token_version" not in user_cols:
        op.add_column(
            "users",
            sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    insp = inspect(op.get_bind())

    user_cols = {c["name"] for c in insp.get_columns("users")}
    if "token_version" in user_cols:
        op.drop_column("users", "token_version")

    if "password_reset_tokens" in insp.get_table_names():
        op.drop_index(
            "ix_password_reset_tokens_token_hash", table_name="password_reset_tokens"
        )
        op.drop_index(
            "ix_password_reset_tokens_user_id", table_name="password_reset_tokens"
        )
        op.drop_table("password_reset_tokens")
