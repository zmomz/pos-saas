"""Per-client ZATCA EGS onboarding state.

Stores the artifacts produced/received during Fatoora onboarding. Secrets
(private key, ZATCA secret) are stored AES-256-GCM encrypted via
``services.zatca.encrypt_secret`` — never in clear text. One row per client.
"""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from core.database import Base


class ZatcaCredentials(Base):
    __tablename__ = "zatca_credentials"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    client_id = Column(Integer, nullable=False, unique=True, index=True)
    environment = Column(String, nullable=False, default="sandbox", server_default="sandbox")

    # Onboarding artifacts.
    private_key_enc = Column(Text, nullable=True)   # AES-256-GCM encrypted PKCS#8 PEM
    csr_pem = Column(Text, nullable=True)           # public PKCS#10 CSR (safe to store)
    egs_serial = Column(String, nullable=True)

    # ZATCA-issued credentials (CSID = binarySecurityToken).
    compliance_request_id = Column(String, nullable=True)
    compliance_csid = Column(Text, nullable=True)
    compliance_secret_enc = Column(Text, nullable=True)
    production_csid = Column(Text, nullable=True)
    production_secret_enc = Column(Text, nullable=True)

    # Hash-chain head: PIH (Previous Invoice Hash) for the next invoice.
    pih = Column(String, nullable=True)

    onboarded = Column(Boolean, nullable=False, default=False, server_default="false")
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
