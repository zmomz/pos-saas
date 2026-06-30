"""Store-credit ledger — an audit row per movement of a customer's store credit (CRM, #221).

Store credit is a customer-attached balance the merchant can grant (goodwill, a
returned item credited back, a loyalty payout) and the customer can later spend.
Unlike a gift card it has no bearer code: it belongs to a ``customers`` row. This
ledger mirrors ``models/gift_card_ledger.py`` — one append-only row per movement
pinning the signed ``amount`` and the resulting ``balance_after`` — so the running
balance is reconstructable and every change is auditable.

Owner-scoped (SEC-02): every row carries the owner's ``user_id`` and the
customer's ``client_id`` so one tenant can neither read nor write another tenant's
credit history.
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from core.database import Base
from core.money import Money


class StoreCreditLedger(Base):
    __tablename__ = "store_credit_ledger"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False, index=True)
    client_id = Column(Integer, nullable=True, index=True)
    customer_id = Column(Integer, nullable=False, index=True)
    # grant / redeem / adjust / refund — the kind of movement.
    entry_type = Column(String, nullable=False)
    # Signed magnitude of the movement: positive credits the balance (grant/refund),
    # negative debits it (redeem). ``Money`` (Numeric(12,2), Decimal half-up) keeps
    # audit amounts penny-exact and free of float drift (REV-03).
    amount = Column(Money, nullable=False, default=0)
    # The customer's store-credit balance immediately after this movement.
    balance_after = Column(Money, nullable=False)
    # Optional link to the sale that drove the movement (e.g. a refund-to-credit).
    transaction_id = Column(Integer, nullable=True, index=True)
    note = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), default=datetime.now)
