"""Gift-card ledger — an audit row per non-sale balance movement (F-038 follow-up).

A gift card's *redemptions* are already recorded as ``giftcard`` tenders on the sale
(`models/payment_tenders.py`); this ledger records the **management** movements that
happen off the sale path — ``reload`` (top-up), ``refund`` (a sale refunded back onto
the card), and ``void`` (cancellation). Each row pins what changed, by how much, and
the resulting ``balance_after``, so a merchant has an audit trail of why a card's
balance moved without a corresponding sale.

Owner-scoped (SEC-02): every row carries the owner's ``user_id`` and the card's
``client_id`` so one client can neither read nor write another client's history.
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String

from core.database import Base


class GiftCardLedger(Base):
    __tablename__ = "gift_card_ledger"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False, index=True)
    client_id = Column(Integer, nullable=False, index=True)
    gift_card_id = Column(Integer, nullable=False, index=True)
    # reload / refund / void
    entry_type = Column(String, nullable=False)
    # The signed-by-convention magnitude of the movement (0 for a void).
    amount = Column(Float, nullable=False, default=0.0)
    # The card's balance immediately after this movement was applied.
    balance_after = Column(Float, nullable=False)
    # Optional link to the sale being refunded (for entry_type == "refund").
    transaction_id = Column(Integer, nullable=True, index=True)
    note = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), default=datetime.now)
