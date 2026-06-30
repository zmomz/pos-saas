"""Customer notes thread — an append-only timestamped note on a customer (CRM, #221).

The ``customers.notes`` column is a single free-form snapshot; this is the running
log behind it. Each row is one immutable note (a call summary, a complaint, a
follow-up) stamped with who wrote it and when, so the merchant's history with a
customer is preserved rather than overwritten on every edit.

Owner-scoped (SEC-02): every row carries the owner's ``user_id`` and the customer's
``client_id`` so one tenant can neither read nor append to another tenant's notes.
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from core.database import Base


class CustomerNote(Base):
    __tablename__ = "customer_notes"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False, index=True)
    client_id = Column(Integer, nullable=True, index=True)
    customer_id = Column(Integer, nullable=False, index=True)
    # The note text. Required and non-blank — an empty note carries no signal.
    body = Column(String, nullable=False)
    # Who logged the note (a staff name), or null when unattributed.
    author = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
