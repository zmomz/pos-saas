from core.database import Base
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String


class Loyalty_programs(Base):
    __tablename__ = "loyalty_programs"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False)
    client_id = Column(Integer, nullable=True)
    name = Column(String, nullable=False)
    points_per_sar = Column(Float, nullable=True)
    redemption_rate = Column(Float, nullable=True)
    min_redemption_points = Column(Integer, nullable=True)
    is_active = Column(Boolean, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)