from core.database import Base
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String


class Customers(Base):
    __tablename__ = "customers"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False)
    name = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    # Buyer VAT registration number for B2B sales (CRM-01). When present on a sale,
    # it flows into the invoice buyer block and routes the document to ZATCA B2B
    # clearance vs B2C reporting (ZA-06 / F-018). Null for ordinary B2C customers.
    vat_number = Column(String, nullable=True)
    notes = Column(String, nullable=True)
    total_purchases = Column(Float, nullable=True)
    visit_count = Column(Integer, nullable=True)
    # Free-form segmentation labels (CRM-04 / F-039), e.g. ["vip", "wholesale"].
    # Stored as a JSON-encoded list of strings (a single TEXT column keeps this on
    # the generic triad without a join table); the router serializes the list in
    # and parses it back out. Null/empty ⇒ untagged. Drives the segment filter in
    # the customer book and pairs with the computed RFM/LTV insights endpoint.
    tags = Column(String, nullable=True)
    # PDPL (SEC-05 / F-050) — Saudi Personal Data Protection Law.
    # ``marketing_consent`` is the explicit, evidenced opt-in required before this
    # customer may be targeted by SMS/WhatsApp marketing (CRM-05). Default False:
    # silence is never consent. ``consent_updated_at`` stamps when the flag last
    # changed so the merchant can evidence when consent was given/withdrawn.
    marketing_consent = Column(Boolean, nullable=True, default=False, server_default="0")
    consent_updated_at = Column(DateTime(timezone=True), nullable=True)
    # Set when the data subject's right-to-erasure request has been honoured: the
    # PII fields (phone/email/vat/notes) are nulled and ``name`` is tombstoned, but
    # the row is retained so fiscal transactions referencing it stay intact (ZATCA
    # 6-year retention overrides erasure for fiscal records — see the data-export
    # retention notice). Null until erased.
    pii_erased_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)