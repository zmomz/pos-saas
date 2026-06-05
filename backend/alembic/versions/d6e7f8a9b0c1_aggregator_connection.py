"""F-060: aggregator ingest — Deliverect-class middleware connection on clients.

Adds the per-client connection the inbound aggregator webhook routes + verifies on:
- ``clients.aggregator_location_id``: the middleware location/outlet id the webhook
  carries; routes an incoming order to this client (indexed, like the Salla store id).
- ``clients.aggregator_webhook_secret``: optional HMAC secret; when set the webhook's
  signature is verified, when unset verification is skipped (sandbox, OPS-08).

New tables for F-055..F-057 (order_ticket_items, kds_tickets, …) are picked up by the
baseline ``create_all``; columns on the pre-existing ``clients`` table need an explicit
add (mirrors the Salla columns in a2b3c4d5e6f7). Guarded idempotently so it only acts
on a database migrated to head before this revision existed. See finding F-060.

Revision ID: d6e7f8a9b0c1
Revises: c8d9e0f1a2b3
Create Date: 2026-06-05 16:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "d6e7f8a9b0c1"
down_revision: Union[str, Sequence[str], None] = "c8d9e0f1a2b3"
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
            op.drop_column(table, column)


def upgrade() -> None:
    insp = inspect(op.get_bind())
    _add_column_if_missing(insp, "clients", sa.Column("aggregator_location_id", sa.String(), nullable=True))
    _add_column_if_missing(insp, "clients", sa.Column("aggregator_webhook_secret", sa.String(), nullable=True))

    if "clients" in insp.get_table_names():
        existing_indexes = {ix["name"] for ix in insp.get_indexes("clients")}
        if "ix_clients_aggregator_location_id" not in existing_indexes:
            op.create_index("ix_clients_aggregator_location_id", "clients", ["aggregator_location_id"])


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if "clients" in insp.get_table_names():
        existing_indexes = {ix["name"] for ix in insp.get_indexes("clients")}
        if "ix_clients_aggregator_location_id" in existing_indexes:
            op.drop_index("ix_clients_aggregator_location_id", table_name="clients")
    _drop_column_if_present(insp, "clients", "aggregator_webhook_secret")
    _drop_column_if_present(insp, "clients", "aggregator_location_id")
