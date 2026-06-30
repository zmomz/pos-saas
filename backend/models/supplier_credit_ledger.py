"""Supplier-credit ledger — an audit row per supplier credit-note movement (M4 Inventory, #224).

When a merchant returns received goods to a vendor, the supplier owes that value
back: a **supplier credit note**. This ledger mirrors ``models/store_credit_ledger.py``
— one append-only row per movement pinning the signed ``amount`` and the resulting
``balance_after`` — so a supplier's outstanding credit balance is reconstructable
and every vendor return is auditable.

Owner-scoped (SEC-02): every row carries the owner's ``user_id`` and the supplier's
``client_id`` so one tenant can neither read nor write another tenant's credit
history. An optional ``purchase_order_id`` links the credit note back to the PO the
returned goods were received on.
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from core.database import Base
from core.money import Money


class SupplierCreditLedger(Base):
    __tablename__ = "supplier_credit_ledger"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False, index=True)
    client_id = Column(Integer, nullable=True, index=True)
    supplier_id = Column(Integer, nullable=False, index=True)
    # credit_note (a vendor return raises credit) / applied (credit spent against a
    # future order) / adjust — the kind of movement.
    entry_type = Column(String, nullable=False)
    # Signed magnitude of the movement: positive raises the supplier's outstanding
    # credit (a vendor return → credit_note), negative draws it down (applied).
    # ``Money`` (Numeric(12,2), Decimal half-up) keeps audit amounts penny-exact
    # and free of float drift (REV-03).
    amount = Column(Money, nullable=False, default=0)
    # The supplier's outstanding credit balance immediately after this movement.
    balance_after = Column(Money, nullable=False)
    # Optional link to the purchase order the returned goods were received on.
    purchase_order_id = Column(Integer, nullable=True, index=True)
    note = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), default=datetime.now)
