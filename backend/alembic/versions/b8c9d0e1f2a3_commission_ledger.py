"""F-029 / RSL-01: commission / revenue-split ledger.

Adds the ``commission_ledger`` table written atomically on each client
subscription payment, decomposing the gross fee into the platform master's cut
(per-client amortized package wholesale) and the agent's net margin. Backs the
Agent Dashboard's real net-margin figure and ``GET /tenant/agent/revenue``.

On a fresh database the baseline revision's ``create_all`` already builds this
table at its current shape, so the create is guarded to be idempotent — it only
acts on a database that was migrated to head before this revision existed.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-06-04 10:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, Sequence[str], None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if "commission_ledger" not in insp.get_table_names():
        op.create_table(
            "commission_ledger",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("agent_id", sa.Integer(), nullable=False),
            sa.Column("client_id", sa.Integer(), nullable=False),
            sa.Column("subscription_payment_id", sa.Integer(), nullable=False),
            sa.Column("package_id", sa.Integer(), nullable=True),
            sa.Column("gross", sa.Float(), nullable=False, server_default="0"),
            sa.Column("master_cut", sa.Float(), nullable=False, server_default="0"),
            sa.Column("agent_net", sa.Float(), nullable=False, server_default="0"),
            sa.Column("billing_cycle", sa.String(), nullable=True),
            sa.Column("period_start", sa.String(), nullable=True),
            sa.Column("period_end", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_commission_ledger_user_id", "commission_ledger", ["user_id"])
        op.create_index("ix_commission_ledger_agent_id", "commission_ledger", ["agent_id"])
        op.create_index("ix_commission_ledger_client_id", "commission_ledger", ["client_id"])
        op.create_index(
            "ix_commission_ledger_subscription_payment_id",
            "commission_ledger",
            ["subscription_payment_id"],
        )


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if "commission_ledger" in insp.get_table_names():
        op.drop_index("ix_commission_ledger_subscription_payment_id", table_name="commission_ledger")
        op.drop_index("ix_commission_ledger_client_id", table_name="commission_ledger")
        op.drop_index("ix_commission_ledger_agent_id", table_name="commission_ledger")
        op.drop_index("ix_commission_ledger_user_id", table_name="commission_ledger")
        op.drop_table("commission_ledger")
