"""F-018 / ZA-06: capture buyer VAT for B2B invoices.

Adds ``customers.vat_number`` (CRM-01 — the saved buyer's VAT registration) and
``transactions.customer_vat_number`` (the buyer VAT captured at sale time). The
captured number flows into the invoice buyer block (UBL/PDF/HTML) and drives the
standard(B2B clearance)-vs-simplified(B2C reporting) routing in
``services/zatca_sale.sign_transaction``. Without it a B2B standard invoice is
structurally impossible (the UBL buyer ``PartyTaxScheme`` is only emitted when a
buyer VAT is present). See finding F-018.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-03 13:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_column_if_missing(insp, table: str, column: str) -> None:
    if table not in insp.get_table_names():
        # Fresh DB: the baseline revision's create_all already built the table at
        # its current shape (with the new column). Nothing to backfill.
        return
    existing = {c["name"] for c in insp.get_columns(table)}
    if column not in existing:
        op.add_column(table, sa.Column(column, sa.String(), nullable=True))


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
    _add_column_if_missing(insp, "customers", "vat_number")
    _add_column_if_missing(insp, "transactions", "customer_vat_number")


def downgrade() -> None:
    insp = inspect(op.get_bind())
    _drop_column_if_present(insp, "transactions", "customer_vat_number")
    _drop_column_if_present(insp, "customers", "vat_number")
