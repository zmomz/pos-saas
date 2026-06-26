"""Processed webhook events — replay/de-dup guard for Moyasar webhooks (SEC-02).

Records each acted-on webhook event id so a redelivery (Moyasar is at-least-once)
cannot re-suspend or re-activate after the fact. ``(source, event_id)`` is unique
so a concurrent duplicate loses the race instead of double-acting.

On a fresh database the baseline ``create_all`` already builds the table, so the
upgrade is guarded to act only when it is absent.

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-06-26 02:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, Sequence[str], None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if "processed_webhook_events" not in insp.get_table_names():
        op.create_table(
            "processed_webhook_events",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("source", sa.String(), nullable=False),
            sa.Column("event_id", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("source", "event_id", name="uq_processed_webhook_event"),
        )
        op.create_index(
            "ix_processed_webhook_events_source", "processed_webhook_events", ["source"]
        )
        op.create_index(
            "ix_processed_webhook_events_event_id", "processed_webhook_events", ["event_id"]
        )


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if "processed_webhook_events" in insp.get_table_names():
        op.drop_table("processed_webhook_events")
