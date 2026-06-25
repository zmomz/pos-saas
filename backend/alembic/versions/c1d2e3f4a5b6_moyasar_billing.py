"""Moyasar billing migration: two-rail billing + drop the revenue-share ledger.

Aligns the schema with the wholesale-quota model:

* agents: drop ``stripe_account_id``; add the agent's own Moyasar account
  (``moyasar_secret_key_enc`` / ``moyasar_publishable_key`` /
  ``moyasar_webhook_secret_enc`` — Rail 2, collects from his merchants), the
  agent's card-on-file for paying the platform (``quota_card_token_enc`` /
  ``quota_card_last4`` / ``quota_card_brand``), and the quota lifecycle
  (``quota_price`` / ``quota_cycle`` / ``quota_status`` / ``quota_dunning_attempts``
  / ``quota_grace_deadline`` / ``next_quota_billing_date``) — Rail 1.
* clients: add the merchant card-on-file (``moyasar_card_token_enc`` /
  ``card_last4`` / ``card_brand``).
* add the ``agent_quota_payments`` table (the platform's own revenue ledger).
* drop the ``commission_ledger`` table (revenue-share is gone — the platform's
  revenue is the wholesale quota, not a cut of merchant payments).

Existing agents are grandfathered with ``quota_status='active'`` (server default);
their first renewal requires a card on file or they enter quota dunning.

On a fresh database the baseline ``create_all`` already builds the new shape, so
every step is guarded to be idempotent (acts only on a DB migrated past the old
shape).

Revision ID: c1d2e3f4a5b6
Revises: 6f708192a3b4
Create Date: 2026-06-25 21:30:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, Sequence[str], None] = "6f708192a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (column name, column) pairs added to a table, only if not already present.
_AGENT_COLUMNS = [
    ("moyasar_secret_key_enc", sa.Column("moyasar_secret_key_enc", sa.String(), nullable=True)),
    ("moyasar_publishable_key", sa.Column("moyasar_publishable_key", sa.String(), nullable=True)),
    ("moyasar_webhook_secret_enc", sa.Column("moyasar_webhook_secret_enc", sa.String(), nullable=True)),
    ("quota_card_token_enc", sa.Column("quota_card_token_enc", sa.String(), nullable=True)),
    ("quota_card_last4", sa.Column("quota_card_last4", sa.String(), nullable=True)),
    ("quota_card_brand", sa.Column("quota_card_brand", sa.String(), nullable=True)),
    ("quota_price", sa.Column("quota_price", sa.Float(), nullable=True)),
    ("quota_cycle", sa.Column("quota_cycle", sa.String(), nullable=True, server_default="monthly")),
    ("quota_status", sa.Column("quota_status", sa.String(), nullable=True, server_default="active")),
    ("quota_dunning_attempts", sa.Column("quota_dunning_attempts", sa.Integer(), nullable=True, server_default="0")),
    ("quota_grace_deadline", sa.Column("quota_grace_deadline", sa.String(), nullable=True)),
    ("next_quota_billing_date", sa.Column("next_quota_billing_date", sa.String(), nullable=True)),
]

_CLIENT_COLUMNS = [
    ("moyasar_card_token_enc", sa.Column("moyasar_card_token_enc", sa.String(), nullable=True)),
    ("card_last4", sa.Column("card_last4", sa.String(), nullable=True)),
    ("card_brand", sa.Column("card_brand", sa.String(), nullable=True)),
]


def _existing_columns(insp, table: str) -> set:
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    insp = inspect(op.get_bind())

    agent_cols = _existing_columns(insp, "agents")
    if agent_cols:
        for name, column in _AGENT_COLUMNS:
            if name not in agent_cols:
                op.add_column("agents", column)
        if "stripe_account_id" in agent_cols:
            op.drop_column("agents", "stripe_account_id")

    client_cols = _existing_columns(insp, "clients")
    if client_cols:
        for name, column in _CLIENT_COLUMNS:
            if name not in client_cols:
                op.add_column("clients", column)

    if "agent_quota_payments" not in insp.get_table_names():
        op.create_table(
            "agent_quota_payments",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("agent_id", sa.Integer(), nullable=False),
            sa.Column("amount", sa.Float(), nullable=False),
            sa.Column("billing_cycle", sa.String(), nullable=True),
            sa.Column("period_start", sa.String(), nullable=True),
            sa.Column("period_end", sa.String(), nullable=True),
            sa.Column("method", sa.String(), nullable=True, server_default="moyasar"),
            sa.Column("reference", sa.String(), nullable=True),
            sa.Column("note", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_agent_quota_payments_user_id", "agent_quota_payments", ["user_id"])
        op.create_index("ix_agent_quota_payments_agent_id", "agent_quota_payments", ["agent_id"])

    if "commission_ledger" in insp.get_table_names():
        for ix in (
            "ix_commission_ledger_subscription_payment_id",
            "ix_commission_ledger_client_id",
            "ix_commission_ledger_agent_id",
            "ix_commission_ledger_user_id",
        ):
            try:
                op.drop_index(ix, table_name="commission_ledger")
            except Exception:  # index may not exist on every dialect
                pass
        op.drop_table("commission_ledger")


def downgrade() -> None:
    insp = inspect(op.get_bind())

    # Recreate the revenue-share ledger (shape only; data is not restored).
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

    insp = inspect(op.get_bind())
    if "agent_quota_payments" in insp.get_table_names():
        op.drop_table("agent_quota_payments")

    client_cols = _existing_columns(insp, "clients")
    for name, _ in _CLIENT_COLUMNS:
        if name in client_cols:
            op.drop_column("clients", name)

    agent_cols = _existing_columns(insp, "agents")
    if agent_cols and "stripe_account_id" not in agent_cols:
        op.add_column("agents", sa.Column("stripe_account_id", sa.String(), nullable=True))
    for name, _ in _AGENT_COLUMNS:
        if name in agent_cols:
            op.drop_column("agents", name)
