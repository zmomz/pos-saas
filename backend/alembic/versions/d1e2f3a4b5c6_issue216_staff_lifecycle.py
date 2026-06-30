"""Issue #216 — staff lifecycle: status/PIN columns + attendance & shift tables.

Adds workforce-management state to the staff directory and two supporting tables:

* ``staff_members.status``   — active / suspended / terminated lifecycle state.
* ``staff_members.pin_hash`` — bcrypt hash of the on-terminal login PIN.
* ``staff_attendance``       — clock-in / clock-out records.
* ``staff_shift_assignments``— rostered shift windows.

On a fresh database the baseline ``create_all`` already builds everything at its
current shape, so each add is guarded to be idempotent — it only backfills a
database migrated to head before this revision existed.

Revision ID: d1e2f3a4b5c6
Revises: c4e5f6a7b8d9
Create Date: 2026-06-30 12:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, Sequence[str], None] = "c4e5f6a7b8d9"
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

    _add_column_if_missing(
        insp,
        "staff_members",
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
    )
    _add_column_if_missing(
        insp, "staff_members", sa.Column("pin_hash", sa.String(), nullable=True)
    )

    tables = set(insp.get_table_names())

    if "staff_attendance" not in tables:
        op.create_table(
            "staff_attendance",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("staff_id", sa.Integer(), nullable=False),
            sa.Column("branch_id", sa.Integer(), nullable=True),
            sa.Column("clock_in", sa.DateTime(timezone=True), nullable=False),
            sa.Column("clock_out", sa.DateTime(timezone=True), nullable=True),
            sa.Column("notes", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
        # Column-level ``index=True`` is ignored by ``op.create_table``; emit the
        # indexes explicitly so they match the ORM model on a real upgrade.
        op.create_index("ix_staff_attendance_user_id", "staff_attendance", ["user_id"])
        op.create_index("ix_staff_attendance_staff_id", "staff_attendance", ["staff_id"])

    if "staff_shift_assignments" not in tables:
        op.create_table(
            "staff_shift_assignments",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("staff_id", sa.Integer(), nullable=False),
            sa.Column("branch_id", sa.Integer(), nullable=True),
            sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("role", sa.String(), nullable=True),
            sa.Column("notes", sa.String(), nullable=True),
            sa.Column("status", sa.String(), nullable=False, server_default="scheduled"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index(
            "ix_staff_shift_assignments_user_id", "staff_shift_assignments", ["user_id"]
        )
        op.create_index(
            "ix_staff_shift_assignments_staff_id", "staff_shift_assignments", ["staff_id"]
        )


def downgrade() -> None:
    insp = inspect(op.get_bind())
    tables = set(insp.get_table_names())
    if "staff_shift_assignments" in tables:
        op.drop_table("staff_shift_assignments")
    if "staff_attendance" in tables:
        op.drop_table("staff_attendance")
    _drop_column_if_present(insp, "staff_members", "pin_hash")
    _drop_column_if_present(insp, "staff_members", "status")
