"""F-044 / FIN-04 / POS-09: cash drawer movements tied to a shift.

Adds the ``cash_movements`` table that records pay-in / pay-out / cash-drop entries
against the open shift, so the close-time drawer reconciliation accounts for cash
that entered or left the till outside a sale, and the Z/X-report can show the
payouts line RPT-06 requires.

On a fresh database the baseline revision's ``create_all`` already builds this table
at its current shape, so the create is guarded to be idempotent — it only acts on a
database that was migrated to head before this revision existed. See finding F-044.

Revision ID: b7c8d9e0f1a2
Revises: a6b7c8d9e0f1
Create Date: 2026-06-05 12:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, Sequence[str], None] = "a6b7c8d9e0f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if "cash_movements" not in insp.get_table_names():
        op.create_table(
            "cash_movements",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("client_id", sa.Integer(), nullable=True),
            sa.Column("shift_id", sa.Integer(), nullable=False),
            sa.Column("movement_type", sa.String(), nullable=False),
            sa.Column("amount", sa.Float(), nullable=False, server_default="0"),
            sa.Column("reason", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_cash_movements_user_id", "cash_movements", ["user_id"])
        op.create_index("ix_cash_movements_client_id", "cash_movements", ["client_id"])
        op.create_index("ix_cash_movements_shift_id", "cash_movements", ["shift_id"])


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if "cash_movements" in insp.get_table_names():
        op.drop_index("ix_cash_movements_shift_id", table_name="cash_movements")
        op.drop_index("ix_cash_movements_client_id", table_name="cash_movements")
        op.drop_index("ix_cash_movements_user_id", table_name="cash_movements")
        op.drop_table("cash_movements")
