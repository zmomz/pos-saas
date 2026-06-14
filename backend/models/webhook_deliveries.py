from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String


class Webhook_deliveries(Base):
    """Append-only log of webhook dispatch outcomes (ISSUE-029 / H24).

    One row per attempted delivery to an endpoint, written by
    ``services.production.record_delivery`` after ``WebhookDispatcher.dispatch``.
    Backs the WebhookManagement "Delivery Logs" tab and its "Deliveries Today"
    stat, which used to consume a non-existent route (swallowed 404).
    """

    __tablename__ = "webhook_deliveries"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False, index=True)
    webhook_id = Column(Integer, nullable=True)
    event = Column(String, nullable=False)
    target_url = Column(String, nullable=False)
    status = Column(String, nullable=False)  # delivered | failed
    status_code = Column(Integer, nullable=True)
    response_time_ms = Column(Integer, nullable=True)
    attempts = Column(Integer, nullable=True)
    error = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now, index=True)
