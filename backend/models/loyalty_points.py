from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String


class Loyalty_points(Base):
    __tablename__ = "loyalty_points"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False)
    client_id = Column(Integer, nullable=True)
    customer_id = Column(Integer, nullable=False)
    points_balance = Column(Integer, nullable=True)
    total_earned = Column(Integer, nullable=True)
    total_redeemed = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)