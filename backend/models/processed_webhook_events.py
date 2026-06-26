"""Processed webhook event ids — replay/de-dup guard (SEC-02).

Moyasar delivers at-least-once: retries and redeliveries can replay the same
event. Each event carries a stable top-level ``id``; we record it the first time
we act on it and ignore any later delivery of the same id, so a replayed failure
event cannot re-suspend (nor a recovery re-activate) an agent after an operator
has intervened. The unique ``(source, event_id)`` makes the claim race-safe — a
concurrent duplicate loses on the constraint instead of double-acting. ``source``
namespaces the id per rail so the platform (Rail 1) and per-agent (Rail 2)
webhooks can never collide on a shared id.
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint

from core.database import Base


class Processed_webhook_events(Base):
    __tablename__ = "processed_webhook_events"
    __table_args__ = (
        UniqueConstraint("source", "event_id", name="uq_processed_webhook_event"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    source = Column(String, nullable=False, index=True)
    event_id = Column(String, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
