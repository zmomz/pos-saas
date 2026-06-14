"""ISSUE-069 (RST): table reservations + walk-in waitlist.

Adds two owner-scoped restaurant tables:

* ``reservations`` — a table booked ahead for a future ``reserved_at`` time; it
  surfaces on the floor (the table tile shows its next upcoming booking) until
  seated or cancelled.
* ``waitlist_entries`` — a queue of walk-in parties; seating an entry to a table
  opens a dine-in order ticket and occupies the table.

On a fresh database the baseline ``create_all`` already builds both tables at
their current shape, so each create is guarded to be idempotent — it only builds
the table on a database migrated to head before this revision existed.

Revision ID: 068d4e5f6a7b
Revises: 067c3d4e5f6a
Create Date: 2026-06-14 19:10:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "068d4e5f6a7b"
down_revision: Union[str, Sequence[str], None] = "067c3d4e5f6a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = inspect(op.get_bind())
    existing = set(insp.get_table_names())

    if "reservations" not in existing:
        op.create_table(
            "reservations",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("client_id", sa.Integer(), nullable=True),
            sa.Column("branch_id", sa.Integer(), nullable=True),
            sa.Column("table_id", sa.Integer(), nullable=True),
            sa.Column("customer_name", sa.String(), nullable=True),
            sa.Column("party_size", sa.Integer(), nullable=True),
            sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("status", sa.String(), nullable=True, server_default="booked"),
            sa.Column("notes", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_reservations_id", "reservations", ["id"])
        op.create_index("ix_reservations_user_id", "reservations", ["user_id"])
        op.create_index("ix_reservations_client_id", "reservations", ["client_id"])
        op.create_index("ix_reservations_table_id", "reservations", ["table_id"])

    if "waitlist_entries" not in existing:
        op.create_table(
            "waitlist_entries",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("client_id", sa.Integer(), nullable=True),
            sa.Column("branch_id", sa.Integer(), nullable=True),
            sa.Column("customer_name", sa.String(), nullable=True),
            sa.Column("party_size", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(), nullable=True, server_default="waiting"),
            sa.Column("notes", sa.String(), nullable=True),
            sa.Column("seated_table_id", sa.Integer(), nullable=True),
            sa.Column("seated_ticket_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_waitlist_entries_id", "waitlist_entries", ["id"])
        op.create_index("ix_waitlist_entries_user_id", "waitlist_entries", ["user_id"])
        op.create_index("ix_waitlist_entries_client_id", "waitlist_entries", ["client_id"])


def downgrade() -> None:
    insp = inspect(op.get_bind())
    existing = set(insp.get_table_names())

    if "waitlist_entries" in existing:
        op.drop_index("ix_waitlist_entries_client_id", table_name="waitlist_entries")
        op.drop_index("ix_waitlist_entries_user_id", table_name="waitlist_entries")
        op.drop_index("ix_waitlist_entries_id", table_name="waitlist_entries")
        op.drop_table("waitlist_entries")

    if "reservations" in existing:
        op.drop_index("ix_reservations_table_id", table_name="reservations")
        op.drop_index("ix_reservations_client_id", table_name="reservations")
        op.drop_index("ix_reservations_user_id", table_name="reservations")
        op.drop_index("ix_reservations_id", table_name="reservations")
        op.drop_table("reservations")
