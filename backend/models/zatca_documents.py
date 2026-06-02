"""Signed ZATCA invoice documents, retained for the statutory period.

Each signed invoice is archived here with its cryptographic stamp, hash, and
chain counter so the business can satisfy ZATCA's 6-year retention requirement
and so reporting/clearance can be retried. ``retention_until`` is computed at
write time from ``ZATCA_RETENTION_YEARS`` (default 6).
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from core.database import Base


class ZatcaDocuments(Base):
    __tablename__ = "zatca_documents"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    client_id = Column(Integer, nullable=False, index=True)
    transaction_id = Column(Integer, nullable=True, index=True)

    invoice_number = Column(String, nullable=False)
    invoice_uuid = Column(String, nullable=True)
    icv = Column(Integer, nullable=True)            # Invoice Counter Value (chain position)
    invoice_hash = Column(String, nullable=True)    # base64 SHA-256 of the canonical XML
    previous_hash = Column(String, nullable=True)   # PIH at signing time
    stamp = Column(Text, nullable=True)             # base64 ECDSA signature
    signed_xml = Column(Text, nullable=True)

    # signed -> reported / cleared / failed
    status = Column(String, nullable=False, default="signed", server_default="signed")
    zatca_response = Column(Text, nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)

    retention_until = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
