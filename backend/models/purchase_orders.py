from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Float, Integer, String


class Purchase_orders(Base):
    __tablename__ = "purchase_orders"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False)
    client_id = Column(Integer, nullable=True)
    supplier_id = Column(Integer, nullable=True)
    order_number = Column(String, nullable=False)
    status = Column(String, nullable=False)
    total_amount = Column(Float, nullable=True)
    items_json = Column(String, nullable=True)
    notes = Column(String, nullable=True)
    expected_date = Column(String, nullable=True)
    received_date = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)