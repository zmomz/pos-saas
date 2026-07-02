"""F-046 / OMN-01..03: omnichannel — Salla channel orders.

Stands up the first omnichannel connector:
- ``channel_orders`` table: the durable record of an online-store order imported via
  webhook and materialized as a POS sale (OMN-03).
- ``clients.salla_store_id`` / ``clients.salla_webhook_secret``: the per-client Salla
  connection used to route + verify an incoming webhook (OMN-01).

On a fresh database the baseline revision's ``create_all`` already builds the table /
columns at their current shape, so every operation is guarded idempotently — it only
acts on a database migrated to head before this revision existed. See finding F-046.

Revision ID: a2b3c4d5e6f7
Revises: f2a3b4c5d6e7
Create Date: 2026-06-04 15:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, Sequence[str], None] = "f2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_column_if_missing(insp, table: str, column: sa.Column) -> None:
    if table not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns(table)}
    if column.name not in existing:
        op.add_column(table, column)


def _drop_column_if_present(insp, table: str, column: str) -> None:
    if table in insp.get_table_names():
        existing = {c["name"] for c in insp.get_columns(table)}
        if column in existing:
            # Drop any index covering this column first — SQLite rejects a
            # DROP COLUMN while an index still references it (the column can be
            # indexed via the ORM's ``index=True`` baked into a create_table).
            # Re-inspect live so an index a prior step already dropped is not
            # dropped twice (a passed-in inspector may be stale).
            for idx in inspect(op.get_bind()).get_indexes(table):
                if column in (idx.get("column_names") or []):
                    op.drop_index(idx["name"], table_name=table)
            op.drop_column(table, column)


def upgrade() -> None:
    insp = inspect(op.get_bind())

    if "channel_orders" not in insp.get_table_names():
        op.create_table(
            "channel_orders",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("client_id", sa.Integer(), nullable=True),
            sa.Column("provider", sa.String(), nullable=False, server_default="salla"),
            sa.Column("external_order_id", sa.String(), nullable=False),
            sa.Column("external_reference", sa.String(), nullable=True),
            sa.Column("transaction_id", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(), nullable=False, server_default="imported"),
            sa.Column("customer_name", sa.String(), nullable=True),
            sa.Column("customer_phone", sa.String(), nullable=True),
            sa.Column("total_amount", sa.Float(), nullable=True),
            sa.Column("currency", sa.String(), nullable=True, server_default="SAR"),
            sa.Column("raw_payload", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_channel_orders_user_id", "channel_orders", ["user_id"])
        op.create_index("ix_channel_orders_client_id", "channel_orders", ["client_id"])
        op.create_index("ix_channel_orders_external_order_id", "channel_orders", ["external_order_id"])
        op.create_index("ix_channel_orders_transaction_id", "channel_orders", ["transaction_id"])

    _add_column_if_missing(insp, "clients", sa.Column("salla_store_id", sa.String(), nullable=True))
    _add_column_if_missing(insp, "clients", sa.Column("salla_webhook_secret", sa.String(), nullable=True))

    # Index the routing key the webhook resolves clients on (matches the model).
    if "clients" in insp.get_table_names():
        existing_indexes = {ix["name"] for ix in insp.get_indexes("clients")}
        if "ix_clients_salla_store_id" not in existing_indexes:
            op.create_index("ix_clients_salla_store_id", "clients", ["salla_store_id"])


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if "clients" in insp.get_table_names():
        existing_indexes = {ix["name"] for ix in insp.get_indexes("clients")}
        if "ix_clients_salla_store_id" in existing_indexes:
            op.drop_index("ix_clients_salla_store_id", table_name="clients")
    _drop_column_if_present(insp, "clients", "salla_webhook_secret")
    _drop_column_if_present(insp, "clients", "salla_store_id")
    if "channel_orders" in insp.get_table_names():
        op.drop_table("channel_orders")
