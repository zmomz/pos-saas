from core.database import Base
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Integer, String


class Receipt_templates(Base):
    __tablename__ = "receipt_templates"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False)
    client_id = Column(Integer, nullable=True)
    name = Column(String, nullable=False)
    header_text = Column(String, nullable=True)
    footer_text = Column(String, nullable=True)
    show_logo = Column(Boolean, nullable=True)
    show_vat_details = Column(Boolean, nullable=True)
    show_qr_code = Column(Boolean, nullable=True)
    paper_size = Column(String, nullable=True)
    font_size = Column(String, nullable=True)
    is_default = Column(Boolean, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)