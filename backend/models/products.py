from core.database import Base
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String


class Products(Base):
    __tablename__ = "products"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False)
    client_id = Column(Integer, nullable=False)
    name = Column(String, nullable=False)
    name_ar = Column(String, nullable=True)
    barcode = Column(String, nullable=True)
    price = Column(Float, nullable=False)
    cost_price = Column(Float, nullable=True)
    quantity = Column(Integer, nullable=True, default=0, server_default='0')
    category = Column(String, nullable=True)
    vat_rate = Column(Float, nullable=True, default=15.0, server_default='15.0')
    is_active = Column(Boolean, nullable=True, default=True, server_default='true')
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)