"""ISSUE-083: active-session management — user_sessions table.

Records each issued refresh token as a session (keyed on its ``jti``) so a user
can list their active sessions and revoke them individually or all-but-current.
Revoking stamps ``revoked_at`` and adds the ``jti`` to the existing revocation
blocklist, so the session's refresh token is rejected at ``/auth/refresh``.

On a fresh database the baseline ``create_all`` already builds this table at its
current shape, so the step is guarded to be idempotent — it only acts on a
database migrated to head before this revision existed.

Revision ID: 6f708192a3b4
Revises: 5e6f70819203
Create Date: 2026-06-15 03:30:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "6f708192a3b4"
down_revision: Union[str, Sequence[str], None] = "5e6f70819203"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = inspect(op.get_bind())

    if "user_sessions" not in insp.get_table_names():
        op.create_table(
            "user_sessions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("user_id", sa.String(length=255), nullable=False),
            sa.Column("jti", sa.String(), nullable=False),
            sa.Column("user_agent", sa.String(), nullable=True),
            sa.Column("ip_address", sa.String(), nullable=True),
            sa.Column("expires_at", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
        op.create_index("ix_user_sessions_jti", "user_sessions", ["jti"], unique=True)
        op.create_index("ix_user_sessions_id", "user_sessions", ["id"])


def downgrade() -> None:
    insp = inspect(op.get_bind())

    if "user_sessions" in insp.get_table_names():
        op.drop_index("ix_user_sessions_id", table_name="user_sessions")
        op.drop_index("ix_user_sessions_jti", table_name="user_sessions")
        op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
        op.drop_table("user_sessions")
