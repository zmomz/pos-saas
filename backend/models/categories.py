from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String


class Categories(Base):
    __tablename__ = "categories"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False)
    # ARC-05: the owning merchant's client id, stamped on write and honoured as a
    # scoping filter alongside ``user_id`` so this entity isolates consistently
    # with the core tables (products, transactions, …) instead of being
    # user-scoped only. Nullable for legacy rows the backfill migration populates.
    client_id = Column(Integer, nullable=True, index=True)
    name = Column(String, nullable=False)
    parent_id = Column(Integer, nullable=True)
    icon = Column(String, nullable=True)
    sort_order = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)