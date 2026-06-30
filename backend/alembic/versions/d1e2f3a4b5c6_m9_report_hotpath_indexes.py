"""M9 reporting: hot-path indexes for the financial-report queries.

The financial/sales reports (P&L, COGS, gross margin, VAT/tax summary, payment
breakdown, cash flow, sales summary) all filter a tenant's rows over a trailing
window — ``client_id == X AND created_at >= start``. Neither ``transactions`` nor
``payment_tenders`` had a composite index covering that predicate, so each report
fell back to a per-client scan that grows with volume and competes with the sale
path. This adds the two composite indexes the new (and existing) report queries
were audited against:

* ``transactions(client_id, created_at)``    — every sales/financial report
* ``payment_tenders(client_id, created_at)`` — payment-breakdown + cash flow

On a fresh database the model metadata already builds these via ``create_all``;
the upgrade is guarded to be idempotent so it is a no-op there.

Revision ID: d1e2f3a4b5c6
Revises: c4e5f6a7b8d9
Create Date: 2026-06-28 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, Sequence[str], None] = "c4e5f6a7b8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# index name -> (table, columns)
_INDEXES = {
    "ix_transactions_client_created": ("transactions", ["client_id", "created_at"]),
    "ix_payment_tenders_client_created": ("payment_tenders", ["client_id", "created_at"]),
}


def _has_index(insp, table: str, name: str) -> bool:
    try:
        return any(ix["name"] == name for ix in insp.get_indexes(table))
    except Exception:
        return False


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    tables = set(insp.get_table_names())
    for name, (table, cols) in _INDEXES.items():
        if table not in tables:
            continue
        if not _has_index(insp, table, name):
            op.create_index(name, table, cols)
        insp = inspect(bind)


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    tables = set(insp.get_table_names())
    for name, (table, _cols) in _INDEXES.items():
        if table not in tables:
            continue
        if _has_index(insp, table, name):
            op.drop_index(name, table_name=table)
        insp = inspect(bind)
