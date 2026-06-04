"""F-050 / SEC-05: PDPL — add customers.marketing_consent + consent_updated_at + pii_erased_at.

Adds three per-customer columns backing Saudi PDPL (Personal Data Protection Law)
compliance:

- ``marketing_consent`` — explicit, evidenced opt-in required before the customer
  may be targeted by SMS/WhatsApp marketing (CRM-05). Default ``False`` (server
  default ``"0"``) — silence is never consent.
- ``consent_updated_at`` — when the consent flag last changed, so the merchant can
  evidence when consent was given or withdrawn.
- ``pii_erased_at`` — set when the data subject's right-to-erasure request has been
  honoured (PII nulled, ``name`` tombstoned, fiscal transactions retained). Null
  until erased.

On a fresh database the baseline revision's ``create_all`` already builds the
``customers`` table at its current shape (with the new columns), so each add is
guarded to be idempotent — it only acts on a database migrated to head before
this revision existed. See finding F-050.

Revision ID: a3b4c5d6e7f8
Revises: d5e6f7a8b9c0
Create Date: 2026-06-04 13:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "a3b4c5d6e7f8"
down_revision: Union[str, Sequence[str], None] = "d5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_column_if_missing(insp, table: str, column: sa.Column) -> None:
    if table not in insp.get_table_names():
        # Fresh DB: the baseline revision's create_all already built the table at
        # its current shape (with the new column). Nothing to backfill.
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
        "customers",
        sa.Column("marketing_consent", sa.Boolean(), nullable=True, server_default="0"),
    )
    _add_column_if_missing(
        insp,
        "customers",
        sa.Column("consent_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    _add_column_if_missing(
        insp,
        "customers",
        sa.Column("pii_erased_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    insp = inspect(op.get_bind())
    _drop_column_if_present(insp, "customers", "pii_erased_at")
    _drop_column_if_present(insp, "customers", "consent_updated_at")
    _drop_column_if_present(insp, "customers", "marketing_consent")
