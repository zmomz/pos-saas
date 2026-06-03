"""ZA-06: add zatca_documents.invoice_subtype (B2B clearance vs B2C reporting).

A signed fiscal document must remember whether it is a *standard* (B2B) invoice —
cleared by Fatoora in real time — or a *simplified* (B2C, and B2B supplies below
the clearance threshold) invoice that is reported within 24h. The decoupled
reporting job (``services/zatca_sale.report_document``) reads this column to route
clearance vs reporting, so the routing decision made at signing time survives the
sale commit. See ZA-06 / finding F-017.

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-06-03 12:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "f5a6b7c8d9e0"
down_revision: Union[str, Sequence[str], None] = "e4f5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if "zatca_documents" not in insp.get_table_names():
        # Fresh DB: the baseline revision's create_all already built the table at
        # its current shape (with invoice_subtype). Nothing to backfill.
        return
    existing = {c["name"] for c in insp.get_columns("zatca_documents")}
    if "invoice_subtype" not in existing:
        op.add_column(
            "zatca_documents",
            sa.Column(
                "invoice_subtype",
                sa.String(),
                server_default="simplified",
                nullable=False,
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if "zatca_documents" in insp.get_table_names():
        existing = {c["name"] for c in insp.get_columns("zatca_documents")}
        if "invoice_subtype" in existing:
            op.drop_column("zatca_documents", "invoice_subtype")
