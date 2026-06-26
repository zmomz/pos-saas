from core.database import Base
from core.money import Money
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
    subscription_fee = Column(Money, nullable=True)
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
    # Card-on-file for subscription billing (Rail 2). The merchant tokenizes their
    # card once via moyasar.js (PAN never reaches us — PAY-09) and the reusable
    # token is stored encrypted (core.crypto); each billing cycle charges it
    # through the owning AGENT's Moyasar account. Null until a card is saved — a
    # charge with no card on file fails closed (402), never a silent free pass.
    moyasar_card_token_enc = Column(String, nullable=True)
    card_last4 = Column(String, nullable=True)
    card_brand = Column(String, nullable=True)
    # Subscription coupon (ISSUE-054). A coupon discounts the subscription fee for
    # a bounded number of billing periods: ``coupon_type`` is 'percentage'|'fixed',
    # ``coupon_value`` the percent/flat amount off, and ``coupon_duration_remaining``
    # the number of charges the coupon still applies to — decremented on each
    # discounted charge and cleared to 0 when spent (after which the full fee is
    # charged). All null/zero ⇒ no coupon.
    coupon_type = Column(String, nullable=True)
    coupon_value = Column(Money, nullable=True)
    coupon_duration_remaining = Column(Integer, nullable=True, default=0, server_default='0')
    # Subscription trial (ISSUE-054). ``trial_end`` is an ISO date; while it is in
    # the future the first charge is deferred (the subscription bills only once the
    # trial ends). Null ⇒ no trial.
    trial_end = Column(String, nullable=True)
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
    # Aggregator ingest — Deliverect-class middleware connection (F-060). A delivery
    # aggregator (Jahez / HungerStation) reaches us only through a Deliverect /
    # Delivery-Hero-POS-partner middleware (the SRS forbids direct aggregator APIs).
    # ``aggregator_location_id`` is the middleware's location/outlet identifier the
    # inbound webhook carries; it routes an order to this client.
    # ``aggregator_webhook_secret`` (optional) verifies the webhook HMAC signature —
    # when unset, verification is skipped (sandbox / graceful degradation, OPS-08).
    # Both null until the client connects an aggregator middleware.
    aggregator_location_id = Column(String, nullable=True, index=True)
    aggregator_webhook_secret = Column(String, nullable=True)
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