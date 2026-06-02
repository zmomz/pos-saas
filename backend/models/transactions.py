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
    status = Column(String, nullable=True, default='completed', server_default='completed')
    zatca_qr = Column(String, nullable=True)
    zatca_hash = Column(String, nullable=True)
    items_json = Column(String, nullable=True)
    customer_name = Column(String, nullable=True)
    customer_phone = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)