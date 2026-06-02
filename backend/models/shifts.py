from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Float, Integer, String


class Shifts(Base):
    __tablename__ = "shifts"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False)
    client_id = Column(Integer, nullable=True)
    branch_id = Column(Integer, nullable=True)
    staff_name = Column(String, nullable=True)
    start_time = Column(String, nullable=True)
    end_time = Column(String, nullable=True)
    opening_cash = Column(Float, nullable=True)
    closing_cash = Column(Float, nullable=True)
    expected_cash = Column(Float, nullable=True)
    cash_difference = Column(Float, nullable=True)
    total_sales = Column(Float, nullable=True)
    total_transactions = Column(Integer, nullable=True)
    status = Column(String, nullable=False)
    notes = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)