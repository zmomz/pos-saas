from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Float, Integer, String


class Transactions(Base):
    __tablename__ = "transactions"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False)
    client_id = Column(Integer, nullable=False)
    invoice_number = Column(String, nullable=False)
    subtotal = Column(Float, nullable=True)
    vat_amount = Column(Float, nullable=True)
    discount_amount = Column(Float, nullable=True, default=0, server_default='0')
    total_amount = Column(Float, nullable=False)
    payment_method = Column(String, nullable=False)
    # JSON array of {"method": str, "amount": float} for split/mixed tenders
    # (cash+card, etc.). Null/empty for single-tender sales where payment_method
    # alone is sufficient. See POS-02 in the gap analysis.
    payment_breakdown = Column(String, nullable=True)
    status = Column(String, nullable=True, default='completed', server_default='completed')
    zatca_qr = Column(String, nullable=True)
    zatca_hash = Column(String, nullable=True)
    items_json = Column(String, nullable=True)
    customer_name = Column(String, nullable=True)
    customer_phone = Column(String, nullable=True)
    # Buyer VAT registration number captured at sale time (F-018). Drives the ZA-06
    # standard(B2B clearance)-vs-simplified(B2C reporting) routing and is rendered
    # into the invoice buyer block (UBL/PDF/HTML). Null for B2C sales.
    customer_vat_number = Column(String, nullable=True)
    # Shift this sale belongs to (POS-04/shifts). Set when an open shift exists at
    # sale time so close_shift can reconcile cash against accumulated sales.
    shift_id = Column(Integer, nullable=True)
    # Branch the sale was rung up at (multi-branch). Enables branch-scoped sales
    # reporting; null for single-branch installs.
    branch_id = Column(Integer, nullable=True)
    # Client-generated id for an offline-queued sale (POS-05). Used to dedupe the
    # sync so re-sending the same queue never double-books a transaction.
    offline_id = Column(String, nullable=True)
    # Original sale this credit note reverses (POS-07 partial/line refunds). Set on
    # a credit_note row so we can sum already-refunded quantities per line across
    # multiple partial refunds and decide refunded vs partial_refunded. Null on a
    # sale row.
    original_transaction_id = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)