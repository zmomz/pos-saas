"""Per-tenant data-retention policy — PDPL data-minimization (#227, SEC-05).

PDPL obliges the merchant (the data controller) not to keep personal data longer
than necessary. This is the merchant's configured retention window for *dormant*
customer PII: ``customer_pii_retention_days`` is how many days a customer may sit
untouched (``customers.updated_at``) before enforcement minimizes their personal
data via the existing PDPL erasure (tombstone name, null phone/email/VAT/notes,
withdraw consent, stamp ``pii_erased_at``). Null ⇒ retention disabled (keep
indefinitely); the policy is opt-in.

One row per tenant, owner-scoped (SEC-02) by ``user_id`` so one tenant can neither
read nor mutate another tenant's window. The fiscal row is retained on erasure —
ZATCA's 6-year invoice-retention obligation overrides erasure for fiscal records,
so only the personal data is minimized.
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from core.database import Base


class DataRetentionPolicy(Base):
    __tablename__ = "data_retention_policies"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    # Owning merchant. One policy per tenant (SEC-02); unique so upserts are stable.
    user_id = Column(String, nullable=False, unique=True, index=True)
    client_id = Column(Integer, nullable=True, index=True)
    # Days a customer may be dormant before their PII is minimized. Null ⇒ disabled.
    customer_pii_retention_days = Column(Integer, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
