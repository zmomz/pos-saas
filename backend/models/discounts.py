from core.database import Base
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String


class Discounts(Base):
    __tablename__ = "discounts"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False)
    # ARC-05: the owning merchant's client id, stamped on write and honoured as a
    # scoping filter alongside ``user_id`` so this entity isolates consistently
    # with the core tables (products, transactions, …) instead of being
    # user-scoped only. Nullable for legacy rows the backfill migration populates.
    client_id = Column(Integer, nullable=True, index=True)
    code = Column(String, nullable=False)
    type = Column(String, nullable=False)
    value = Column(Float, nullable=False)
    min_purchase = Column(Float, nullable=True)
    is_active = Column(Boolean, nullable=True)
    usage_count = Column(Integer, nullable=True)
    max_uses = Column(Integer, nullable=True)
    # PRC-02 / PRC-01 validity window: a coupon/promo is only honoured between
    # ``starts_at`` and ``ends_at`` (either bound NULL ⇒ open-ended on that side).
    # This is what turns a flat code into a time-window promotion (e.g. a campaign
    # that runs Jun 1–30, or a "happy-hour" code scheduled to go live later).
    starts_at = Column(DateTime(timezone=True), nullable=True)
    ends_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)