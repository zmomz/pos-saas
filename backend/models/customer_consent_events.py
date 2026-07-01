"""Customer consent-event log — an append-only PDPL consent trail (#227, SEC-05).

The ``customers`` row carries only the LATEST consent state (``marketing_consent``
plus ``consent_updated_at``); that timestamp is overwritten on every change, so the
history of "given on X, withdrawn on Y, re-given on Z" is lost. This is the running
log behind that snapshot: each consent change writes its own immutable, timestamped
row, so the merchant (the data controller) can *evidence* when consent was granted
or withdrawn — the audit trail PDPL requires.

Owner-scoped (SEC-02): every row carries the owner's ``user_id`` and the customer's
``client_id`` so one tenant can neither read nor append to another tenant's trail.
"""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from core.database import Base


class CustomerConsentEvent(Base):
    __tablename__ = "customer_consent_events"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False, index=True)
    client_id = Column(Integer, nullable=True, index=True)
    customer_id = Column(Integer, nullable=False, index=True)
    # Which consent this event concerns. Only "marketing" exists today (CRM-05); the
    # column leaves room for future consent kinds (analytics, third-party sharing…).
    consent_type = Column(String, nullable=False, default="marketing", server_default="marketing")
    # The NEW state this event set: True = opt-in granted, False = withdrawn.
    granted = Column(Boolean, nullable=False)
    # Where the change originated: "create", "update", or "erase" (PDPL erasure
    # withdraws consent). Kept generic so future channels (a consent portal) fit.
    source = Column(String, nullable=False)
    # Who made the change (a user id/name), or null when unattributed.
    actor = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
