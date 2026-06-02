"""ZATCA Phase-2: credentials + retained signed documents

Adds the per-client EGS onboarding store (`zatca_credentials`) and the retained
signed-invoice archive (`zatca_documents`) introduced in Phase B.

Revision ID: b1f2c3d4e5f6
Revises: 46b401dd2b89
Create Date: 2026-06-02 12:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1f2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "46b401dd2b89"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "zatca_credentials",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=False),
        sa.Column("environment", sa.String(), server_default="sandbox", nullable=False),
        sa.Column("private_key_enc", sa.Text(), nullable=True),
        sa.Column("csr_pem", sa.Text(), nullable=True),
        sa.Column("egs_serial", sa.String(), nullable=True),
        sa.Column("compliance_request_id", sa.String(), nullable=True),
        sa.Column("compliance_csid", sa.Text(), nullable=True),
        sa.Column("compliance_secret_enc", sa.Text(), nullable=True),
        sa.Column("production_csid", sa.Text(), nullable=True),
        sa.Column("production_secret_enc", sa.Text(), nullable=True),
        sa.Column("pih", sa.String(), nullable=True),
        sa.Column("onboarded", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_zatca_credentials_id"), "zatca_credentials", ["id"], unique=False)
    op.create_index(
        op.f("ix_zatca_credentials_client_id"), "zatca_credentials", ["client_id"], unique=True
    )

    op.create_table(
        "zatca_documents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=False),
        sa.Column("transaction_id", sa.Integer(), nullable=True),
        sa.Column("invoice_number", sa.String(), nullable=False),
        sa.Column("invoice_uuid", sa.String(), nullable=True),
        sa.Column("icv", sa.Integer(), nullable=True),
        sa.Column("invoice_hash", sa.String(), nullable=True),
        sa.Column("previous_hash", sa.String(), nullable=True),
        sa.Column("stamp", sa.Text(), nullable=True),
        sa.Column("signed_xml", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), server_default="signed", nullable=False),
        sa.Column("zatca_response", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_zatca_documents_id"), "zatca_documents", ["id"], unique=False)
    op.create_index(
        op.f("ix_zatca_documents_client_id"), "zatca_documents", ["client_id"], unique=False
    )
    op.create_index(
        op.f("ix_zatca_documents_transaction_id"), "zatca_documents", ["transaction_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_zatca_documents_transaction_id"), table_name="zatca_documents")
    op.drop_index(op.f("ix_zatca_documents_client_id"), table_name="zatca_documents")
    op.drop_index(op.f("ix_zatca_documents_id"), table_name="zatca_documents")
    op.drop_table("zatca_documents")
    op.drop_index(op.f("ix_zatca_credentials_client_id"), table_name="zatca_credentials")
    op.drop_index(op.f("ix_zatca_credentials_id"), table_name="zatca_credentials")
    op.drop_table("zatca_credentials")
