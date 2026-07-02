"""M7·Compliance / issue-227: customer consent-event trail.

Adds the ``customer_consent_events`` table — an append-only, timestamped record of
every marketing-consent change (given/withdrawn) behind the single-value
``customers.marketing_consent`` / ``consent_updated_at`` snapshot, so the merchant
can evidence *when* consent changed (PDPL / SEC-05).

On a fresh database the baseline revision's ``create_all`` already builds the table
at its current shape, so the create is guarded idempotently — it only acts on a
database migrated to head before this revision existed.

Revision ID: c72a9f1e4b30
Revises: 225adm0a1b2c
Create Date: 2026-07-01 03:20:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "c72a9f1e4b30"
down_revision: Union[str, Sequence[str], None] = "225adm0a1b2c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if "customer_consent_events" not in insp.get_table_names():
        op.create_table(
            "customer_consent_events",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("client_id", sa.Integer(), nullable=True),
            sa.Column("customer_id", sa.Integer(), nullable=False),
            sa.Column(
                "consent_type", sa.String(), nullable=False, server_default="marketing"
            ),
            sa.Column("granted", sa.Boolean(), nullable=False),
            sa.Column("source", sa.String(), nullable=False),
            sa.Column("actor", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index(
            "ix_customer_consent_events_user_id", "customer_consent_events", ["user_id"]
        )
        op.create_index(
            "ix_customer_consent_events_client_id", "customer_consent_events", ["client_id"]
        )
        op.create_index(
            "ix_customer_consent_events_customer_id",
            "customer_consent_events",
            ["customer_id"],
        )


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if "customer_consent_events" in insp.get_table_names():
        op.drop_table("customer_consent_events")
