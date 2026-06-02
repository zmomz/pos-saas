from core.database import Base
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String


class Clients(Base):
    __tablename__ = "clients"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False)
    agent_id = Column(Integer, nullable=False)
    business_name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    subscription_fee = Column(Float, nullable=True)
    is_active = Column(Boolean, nullable=True, default=True, server_default='true')
    vat_number = Column(String, nullable=True)
    invoice_counter = Column(Integer, nullable=True, default=0, server_default='0')
    language_preference = Column(String, nullable=True, default='en', server_default='en')
    zatca_enabled = Column(Boolean, nullable=True, default=False, server_default='false')
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)