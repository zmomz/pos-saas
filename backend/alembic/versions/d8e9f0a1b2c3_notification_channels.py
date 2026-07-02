"""ISSUE-214 (M10 / parity #8): add WhatsApp + push channel toggles to profiles.

Adds the ``whatsapp_alerts`` and ``push_alerts`` per-channel master switches to
``user_profiles`` so a user can choose which channels the notification composer
may reach them on. Both default **off** so an upgrade never starts messaging a
user over a channel they never opted into.

Idempotent: skips a column that already exists (a fresh DB builds the table at
its current shape via the baseline ``create_all``).

Revision ID: d8e9f0a1b2c3
Revises: d1e2f3a4b5c6
Create Date: 2026-06-30 00:45:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "d8e9f0a1b2c3"
down_revision: Union[str, Sequence[str], None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_columns() -> set:
    insp = inspect(op.get_bind())
    if "user_profiles" not in insp.get_table_names():
        return set()
    return {col["name"] for col in insp.get_columns("user_profiles")}


def upgrade() -> None:
    cols = _existing_columns()
    if not cols:
        return
    if "whatsapp_alerts" not in cols:
        op.add_column(
            "user_profiles",
            sa.Column("whatsapp_alerts", sa.Boolean(), nullable=False, server_default="false"),
        )
    if "push_alerts" not in cols:
        op.add_column(
            "user_profiles",
            sa.Column("push_alerts", sa.Boolean(), nullable=False, server_default="false"),
        )


def downgrade() -> None:
    cols = _existing_columns()
    if "push_alerts" in cols:
        op.drop_column("user_profiles", "push_alerts")
    if "whatsapp_alerts" in cols:
        op.drop_column("user_profiles", "whatsapp_alerts")
