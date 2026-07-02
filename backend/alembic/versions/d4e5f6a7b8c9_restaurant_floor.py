"""F-045 / RST-01..03 + CL-02: restaurant floor, tables, order tickets + business_type.

Stands up the first slice of the restaurant vertical:

* ``clients.business_type`` (retail / restaurant / both) — the discriminator that
  gates the restaurant POS mode; existing clients backfill to ``retail``.
* ``floor_zones`` — named areas of a branch's floor (RST-01).
* ``restaurant_tables`` — seatable tables with a state (free / occupied /
  bill_printed) for the floor map (RST-01).
* ``order_tickets`` — an open order against a table (RST-02/03).

On a fresh database the baseline revision's ``create_all`` already builds these at
their current shape, so each step here is guarded to be idempotent — it only acts
on a database that was migrated to head before this revision existed. See finding
F-045.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-03 16:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_column_if_missing(insp, table: str, column: str, col: sa.Column) -> None:
    if table not in insp.get_table_names():
        # Fresh DB: the baseline revision's create_all already built the table at
        # its current shape (with the new column). Nothing to backfill.
        return
    existing = {c["name"] for c in insp.get_columns(table)}
    if column not in existing:
        op.add_column(table, col)


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

    # CL-02: business type discriminator.
    _add_column_if_missing(
        insp,
        "clients",
        "business_type",
        sa.Column("business_type", sa.String(), server_default="retail", nullable=True),
    )

    if "floor_zones" not in insp.get_table_names():
        op.create_table(
            "floor_zones",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("client_id", sa.Integer(), nullable=True),
            sa.Column("branch_id", sa.Integer(), nullable=True),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_floor_zones_user_id", "floor_zones", ["user_id"])
        op.create_index("ix_floor_zones_client_id", "floor_zones", ["client_id"])

    if "restaurant_tables" not in insp.get_table_names():
        op.create_table(
            "restaurant_tables",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("client_id", sa.Integer(), nullable=True),
            sa.Column("branch_id", sa.Integer(), nullable=True),
            sa.Column("zone_id", sa.Integer(), nullable=True),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("seats", sa.Integer(), nullable=True, server_default="4"),
            sa.Column("state", sa.String(), nullable=True, server_default="free"),
            sa.Column("current_ticket_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_restaurant_tables_user_id", "restaurant_tables", ["user_id"])
        op.create_index("ix_restaurant_tables_client_id", "restaurant_tables", ["client_id"])
        op.create_index("ix_restaurant_tables_zone_id", "restaurant_tables", ["zone_id"])

    if "order_tickets" not in insp.get_table_names():
        op.create_table(
            "order_tickets",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("client_id", sa.Integer(), nullable=True),
            sa.Column("branch_id", sa.Integer(), nullable=True),
            sa.Column("table_id", sa.Integer(), nullable=True),
            sa.Column("order_type", sa.String(), nullable=True, server_default="dine_in"),
            sa.Column("status", sa.String(), nullable=True, server_default="open"),
            sa.Column("customer_name", sa.String(), nullable=True),
            sa.Column("party_size", sa.Integer(), nullable=True),
            sa.Column("notes", sa.String(), nullable=True),
            sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_order_tickets_user_id", "order_tickets", ["user_id"])
        op.create_index("ix_order_tickets_client_id", "order_tickets", ["client_id"])
        op.create_index("ix_order_tickets_table_id", "order_tickets", ["table_id"])


def downgrade() -> None:
    insp = inspect(op.get_bind())
    for table in ("order_tickets", "restaurant_tables", "floor_zones"):
        if table in insp.get_table_names():
            op.drop_table(table)
    _drop_column_if_present(insp, "clients", "business_type")
