from core.database import Base
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String


class Discounts(Base):
    __tablename__ = "discounts"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False)
    code = Column(String, nullable=False)
    type = Column(String, nullable=False)
    value = Column(Float, nullable=False)
    min_purchase = Column(Float, nullable=True)
    is_active = Column(Boolean, nullable=True)
    usage_count = Column(Integer, nullable=True)
    max_uses = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)