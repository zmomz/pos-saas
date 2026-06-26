"""Billing idempotency — per-period unique key on the payment ledgers (FIN-04).

A recurring charge (merchant subscription, Rail 2; agent quota, Rail 1) is billed
once per billing period, but nothing in the DB enforced that: a double-click or a
scheduler-vs-manual race could record — and charge — the same period twice. This
adds a nullable ``period_key`` column (set to the period start for an actual
settled gateway charge; NULL for proration/manual records, which are exempt) and a
unique constraint per ledger so the database arbitrates a true race:

* ``subscription_payments``: unique (client_id, period_key)
* ``agent_quota_payments``:  unique (agent_id, period_key)

NULL ``period_key`` rows never collide (NULLs are distinct in SQLite/Postgres), so
proration and manually-recorded payments are unaffected.

On a fresh database the baseline ``create_all`` already builds the column and the
constraint from the models, so the upgrade only acts when they are absent.

Revision ID: fb1c2d3e4a5b
Revises: fa1b2c3d4e5f
Create Date: 2026-06-26 15:50:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "fb1c2d3e4a5b"
down_revision: Union[str, Sequence[str], None] = "fa1b2c3d4e5f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# table -> (scope column, unique-constraint name)
_LEDGERS = {
    "subscription_payments": ("client_id", "uq_subscription_payment_client_period"),
    "agent_quota_payments": ("agent_id", "uq_quota_payment_agent_period"),
}


def _has_column(insp, table: str, col: str) -> bool:
    return any(c["name"] == col for c in insp.get_columns(table))


def _has_constraint(insp, table: str, name: str) -> bool:
    try:
        uniques = insp.get_unique_constraints(table)
    except NotImplementedError:
        uniques = []
    if any(uc.get("name") == name for uc in uniques):
        return True
    return any(ix["name"] == name for ix in insp.get_indexes(table))


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    tables = set(insp.get_table_names())

    for table, (scope_col, cname) in _LEDGERS.items():
        if table not in tables:
            continue  # table built later with the column+constraint already on it
        if not _has_column(insp, table, "period_key"):
            op.add_column(table, sa.Column("period_key", sa.String(), nullable=True))
        # Re-inspect so the constraint check / batch rebuild see the new column.
        insp = inspect(bind)
        if not _has_constraint(insp, table, cname):
            with op.batch_alter_table(table, schema=None) as batch_op:
                batch_op.create_unique_constraint(cname, [scope_col, "period_key"])
            insp = inspect(bind)


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    tables = set(insp.get_table_names())

    for table, (_scope_col, cname) in _LEDGERS.items():
        if table not in tables:
            continue
        if _has_constraint(insp, table, cname):
            with op.batch_alter_table(table, schema=None) as batch_op:
                batch_op.drop_constraint(cname, type_="unique")
        insp = inspect(bind)
        if _has_column(insp, table, "period_key"):
            with op.batch_alter_table(table, schema=None) as batch_op:
                batch_op.drop_column("period_key")
        insp = inspect(bind)
