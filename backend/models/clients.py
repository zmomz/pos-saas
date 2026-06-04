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
    invoice_counter = Column(Integer, nullable=True, default=0, server_default='0')
    language_preference = Column(String, nullable=True, default='en', server_default='en')
    zatca_enabled = Column(Boolean, nullable=True, default=False, server_default='false')
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)