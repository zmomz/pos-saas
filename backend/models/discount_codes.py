from core.database import Base
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String


class DiscountCodes(Base):
    """A single-use / unique discount code (ISSUE-059, PRC).

    Distinct from ``Discounts`` (one reusable code with a ``usage_count``/``max_uses``
    cap counted up across many sales). Each ``DiscountCodes`` row is one *unique*
    code, minted in a ``batch_id`` group, redeemable **exactly once**: ``redeemed``
    flips the first time it is applied and a second redemption is rejected. The same
    ``starts_at``/``ends_at`` validity-window semantics as ``Discounts`` apply
    (either bound NULL ⇒ open-ended on that side).
    """

    __tablename__ = "discount_codes"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False, index=True)
    # ARC-05: the owning merchant's client id, stamped at mint time so codes scope
    # consistently with the core tables (products, transactions, …) instead of being
    # user-scoped only. Nullable for legacy rows the backfill migration populates.
    client_id = Column(Integer, nullable=True, index=True)
    # Codes are minted in batches; the batch id groups one generation run.
    batch_id = Column(String, nullable=False, index=True)
    code = Column(String, nullable=False, index=True)
    type = Column(String, nullable=False)
    value = Column(Float, nullable=False)
    min_purchase = Column(Float, nullable=True)
    # One-shot redemption state: ``redeemed`` flips True the first (only) time the
    # code is applied; ``redeemed_at`` records when.
    redeemed = Column(Boolean, nullable=False, default=False)
    redeemed_at = Column(DateTime(timezone=True), nullable=True)
    # Validity window (PRC-02), same semantics as Discounts.
    starts_at = Column(DateTime(timezone=True), nullable=True)
    ends_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
