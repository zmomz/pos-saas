from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String


class Api_usage(Base):
    __tablename__ = "api_usage"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False)  # the *actor* — the JWT ``sub`` that made the request
    # The owning merchant this metering row belongs to (resolved via the tenant
    # scope), so a merchant's usage query aggregates all staff activity rather than
    # only the owner's own requests (finding H4).
    owner_user_id = Column(String, nullable=True, index=True)
    agent_id = Column(Integer, nullable=True)
    endpoint = Column(String, nullable=False)
    method = Column(String, nullable=False)
    status_code = Column(Integer, nullable=True)
    response_time_ms = Column(Integer, nullable=True)
    request_date = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)