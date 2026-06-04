"""Persisted notification center rows (UX-08, F-052).

The notifications page (``/notifications``) used to *synthesize* its feed on every
request from low-stock + recent transactions, with a ``mark-read`` that returned
success but persisted nothing — so the read state was a lie across reloads, and a
field mismatch (``items`` vs ``notifications``) meant the page never rendered a
single item. This is the persisted backing for that center.

Each row is owned by ``user_id`` (the merchant's own login account) so the list and
``mark-read`` scope to the owner exactly like every other entity — one client can
never see or acknowledge another client's notifications (SEC-02).

System alerts (IB §UX-08 feed: low-stock, ZATCA-failed, subscription) are
*materialized idempotently* into this table on read: each carries a stable
``dedupe_key`` (e.g. ``low_stock:<product_id>``) so re-materialization updates the
existing row's message in place and **preserves ``is_read``** — that is what makes a
"mark as read" survive a refetch. ``type`` is one of low_stock / zatca_failed /
subscription / system (KDS is RST-vision, deferred).
"""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from core.database import Base


class Notifications(Base):
    __tablename__ = "notifications"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    # Owner — the merchant's own login account (SEC-02 scoping).
    user_id = Column(String, nullable=False, index=True)
    client_id = Column(Integer, nullable=True, index=True)
    # low_stock / zatca_failed / subscription / system
    type = Column(String, nullable=False, default="system", server_default="system")
    title = Column(String, nullable=True)
    message = Column(Text, nullable=False)
    # Stable per (user_id, source) so system alerts upsert instead of duplicating,
    # preserving is_read across re-materialization. NULL for ad-hoc notifications.
    dedupe_key = Column(String, nullable=True, index=True)
    is_read = Column(Boolean, nullable=False, default=False, server_default="0")
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
