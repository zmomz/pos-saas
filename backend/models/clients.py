from core.database import Base
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String


class Clients(Base):
    __tablename__ = "clients"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False)
    agent_id = Column(Integer, nullable=False)
    business_name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    subscription_fee = Column(Float, nullable=True)
    # Subscription lifecycle (CL-03/CL-04). billing_cycle is 'monthly'|'yearly';
    # subscription_status is 'active'|'past_due'|'suspended'. next_billing_date is
    # an ISO date string advanced each time the client pays.
    billing_cycle = Column(String, nullable=True, default='monthly', server_default='monthly')
    subscription_status = Column(String, nullable=True, default='active', server_default='active')
    next_billing_date = Column(String, nullable=True)
    # Dunning state machine (CL-06). A failed retry walks the subscription
    # active -> past_due -> dunning -> suspended; a successful charge / pay resets
    # both fields and returns to active. ``dunning_attempts`` counts consecutive
    # failed charge attempts; ``grace_deadline`` is the ISO date by which the
    # client must pay before the next retry escalates / suspends (PRN-09 notice).
    dunning_attempts = Column(Integer, nullable=True, default=0, server_default='0')
    grace_deadline = Column(String, nullable=True)
    is_active = Column(Boolean, nullable=True, default=True, server_default='true')
    # Retail / restaurant / both — picked at provisioning / first-login (CL-02).
    # Drives POS mode and gates the restaurant vertical (RST-*, F-045). Defaults
    # to 'retail' so existing clients keep the retail-only experience.
    business_type = Column(String, nullable=True, default='retail', server_default='retail')
    vat_number = Column(String, nullable=True)
    # Omnichannel — Salla connection (OMN-01, F-046). ``salla_store_id`` is the
    # merchant/store identifier the Salla webhook carries; it routes an incoming
    # online order to this client. ``salla_webhook_secret`` (optional) verifies the
    # webhook HMAC signature — when unset, signature verification is skipped
    # (sandbox / graceful degradation, OPS-08). Both null until the client connects
    # their Salla store.
    salla_store_id = Column(String, nullable=True, index=True)
    salla_webhook_secret = Column(String, nullable=True)
    invoice_counter = Column(Integer, nullable=True, default=0, server_default='0')
    language_preference = Column(String, nullable=True, default='en', server_default='en')
    # ZA-09: per-client e-invoicing opt-out, honored on the sale path
    # (services/zatca_sale.py::is_zatca_enabled). ZATCA is the Saudi default so a
    # new client is provisioned with it ON; an agent may switch it OFF for a
    # non-VAT-registered merchant, whose sales then complete as simplified
    # non-tax receipts (no stamp/QR, no zatca_documents row). Only an explicit
    # False disables — a legacy NULL is treated as enabled (de-facto always-signed).
    zatca_enabled = Column(Boolean, nullable=True, default=True, server_default='true')
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)