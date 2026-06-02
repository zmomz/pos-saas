from core.database import Base
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Integer, String


class Webhooks(Base):
    __tablename__ = "webhooks"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False)
    client_id = Column(Integer, nullable=True)
    name = Column(String, nullable=False)
    url = Column(String, nullable=False)
    events = Column(String, nullable=False)
    secret_key = Column(String, nullable=True)
    is_active = Column(Boolean, nullable=True)
    last_triggered = Column(String, nullable=True)
    failure_count = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)