"""Captured payment tenders for a sale (PAY-01/05/09, F-001/F-003).

Each tender line of a (possibly split) sale records **how it was paid and the
proof it was approved** — the acquirer network, the approval/auth code, the RRN
(retrieval reference number), the gateway transaction reference (for refund-to-
origin), and at most the card's last 4 digits + a gateway token. This is what
turns a "card"/"Mada" button from a label into a real captured tender.

**PCI scope minimization (PAY-09 / SEC-06): a PAN never touches our servers.**
This table intentionally has **no** ``pan`` / ``card_number`` column — only the
gateway-issued token and the last 4 digits are stored. The test suite asserts
the absence of any PAN-bearing column so this invariant is caught forever.

States: ``authorized`` (approved, not yet settled into a sale), ``captured``
(approved and tied to a committed sale — the common case), ``declined`` (the
gateway refused; the sale is rolled back so a declined tender is normally never
persisted on the sale path), ``refunded`` (reversed to the original tender —
PAY-10, future).
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String

from core.database import Base


class PaymentTenders(Base):
    __tablename__ = "payment_tenders"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False, index=True)
    client_id = Column(Integer, nullable=False, index=True)
    # The sale this tender settled. Null for a standalone pre-authorization
    # captured via POST /payments/charge before being attached to a sale.
    transaction_id = Column(Integer, nullable=True, index=True)

    # cash / card / mada / applepay / stcpay / tabby / tamara / transfer / loyalty.
    tender_type = Column(String, nullable=False)
    amount = Column(Float, nullable=False)

    # ---- Gateway capture proof (NEVER a PAN) ----
    network = Column(String, nullable=True)        # MADA / VISA / MASTERCARD / APPLEPAY / STCPAY / ...
    approval_code = Column(String, nullable=True)  # acquirer approval / authorization code
    rrn = Column(String, nullable=True)            # retrieval reference number
    gateway_ref = Column(String, nullable=True)    # gateway transaction id (refund-to-origin handle)
    last4 = Column(String, nullable=True)          # last 4 digits only — never the full PAN
    token = Column(String, nullable=True)          # gateway card token (tokenized, no PAN)
    gateway = Column(String, nullable=True)        # which gateway captured it: sandbox / moyasar / ...

    # authorized / captured / declined / refunded
    status = Column(String, nullable=False, default="captured", server_default="captured")
    decline_reason = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
