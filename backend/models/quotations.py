from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Float, Integer, String


class Quotations(Base):
    """A price quotation (عرض سعر) — a non-fiscal pre-sale document.

    Mirrors a transaction's shape (line items + totals) but is explicitly NOT a
    ZATCA tax invoice: it has no invoice counter, QR, or cryptographic stamp. Its
    printable document (rendered server-side) is always Arabic per SRS §7.
    """
    __tablename__ = "quotations"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False)
    client_id = Column(Integer, nullable=True)
    quote_number = Column(String, nullable=True)
    customer_name = Column(String, nullable=True)
    customer_phone = Column(String, nullable=True)
    items_json = Column(String, nullable=True)
    subtotal = Column(Float, nullable=True, default=0, server_default='0')
    vat_amount = Column(Float, nullable=True, default=0, server_default='0')
    discount_amount = Column(Float, nullable=True, default=0, server_default='0')
    total_amount = Column(Float, nullable=True, default=0, server_default='0')
    valid_until = Column(DateTime(timezone=True), nullable=True)
    status = Column(String, nullable=True, default='draft', server_default='draft')
    notes = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
