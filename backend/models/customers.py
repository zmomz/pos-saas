from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Float, Integer, String


class Customers(Base):
    __tablename__ = "customers"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False)
    name = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    # Buyer VAT registration number for B2B sales (CRM-01). When present on a sale,
    # it flows into the invoice buyer block and routes the document to ZATCA B2B
    # clearance vs B2C reporting (ZA-06 / F-018). Null for ordinary B2C customers.
    vat_number = Column(String, nullable=True)
    notes = Column(String, nullable=True)
    total_purchases = Column(Float, nullable=True)
    visit_count = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)