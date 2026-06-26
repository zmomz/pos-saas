"""Gift cards / store credit (CRM-03 / PRC-05, F-038).

A gift card is **prepaid store credit** a merchant issues to a customer; it is then
redeemed as a *tender* on a sale (PRC-05), decrementing its ``balance`` atomically
inside the sale transaction — so a rolled-back sale never spends it and concurrent
redemptions cannot overdraw it (the same conditional-UPDATE pattern as a discount
``max_uses`` cap). The ``code`` is the **bearer secret** (anyone holding it can
redeem), so it is generated server-side from a CSPRNG, never trusted from the
client; only its last 4 digits are echoed on a sale's tender row.

States:
  * ``active``   — has balance and is redeemable.
  * ``redeemed`` — balance exhausted (flipped automatically when it reaches 0).
  * ``expired``  — past ``expiry_date`` (judged at redemption time).
  * ``void``     — cancelled by the merchant.

Owner-scoping (SEC-02): every read/write filters on ``user_id`` so one client can
neither see nor redeem another client's cards.
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from core.database import Base
from core.money import Money


class Gift_cards(Base):
    __tablename__ = "gift_cards"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False, index=True)
    client_id = Column(Integer, nullable=False, index=True)
    # The bearer code (unguessable, CSPRNG-generated). Indexed for redemption lookup.
    code = Column(String, nullable=False, index=True)
    currency = Column(String, nullable=False, default="SAR", server_default="SAR")
    # The face value the card was issued with (never mutated) and the live balance.
    # ``Money`` (Numeric(12,2), Decimal half-up) so balances stay penny-exact and
    # never inherit float subtraction drift (FIN-03).
    initial_balance = Column(Money, nullable=False)
    balance = Column(Money, nullable=False)
    # active / redeemed / expired / void
    status = Column(String, nullable=False, default="active", server_default="active")
    # Optional expiry; NULL means the card never expires.
    expiry_date = Column(DateTime(timezone=True), nullable=True)
    # Optional CRM link (the customer the card was issued to).
    customer_id = Column(Integer, nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
