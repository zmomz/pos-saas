"""M7·Compliance / issue-227: per-tenant data-retention policy.

Adds the ``data_retention_policies`` table — one row per tenant holding the
dormant-PII retention window (``customer_pii_retention_days``). PDPL (SEC-05)
data-minimization: enforcement minimizes the PII of customers untouched beyond
the window via the existing erasure (tombstone name, null contact PII, withdraw
consent), keeping the fiscal row for ZATCA's 6-year retention.

On a fresh database the baseline revision's ``create_all`` already builds the
table at its current shape, so the create is guarded idempotently — it only acts
on a database migrated to head before this revision existed.

Revision ID: 5defecb7cf98
Revises: c72a9f1e4b30
Create Date: 2026-07-01 03:30:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "5defecb7cf98"
down_revision: Union[str, Sequence[str], None] = "c72a9f1e4b30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if "data_retention_policies" not in insp.get_table_names():
        op.create_table(
            "data_retention_policies",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("client_id", sa.Integer(), nullable=True),
            sa.Column("customer_pii_retention_days", sa.Integer(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index(
            "ix_data_retention_policies_user_id",
            "data_retention_policies",
            ["user_id"],
            unique=True,
        )
        op.create_index(
            "ix_data_retention_policies_client_id",
            "data_retention_policies",
            ["client_id"],
        )


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if "data_retention_policies" in insp.get_table_names():
        op.drop_table("data_retention_policies")
