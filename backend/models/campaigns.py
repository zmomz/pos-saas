"""Marketing campaigns (CRM, #221).

A campaign is a named marketing send a merchant defines on a channel (sms/email)
carrying a message, optionally targeting one customer group. ``target_group_id``
null ⇒ the campaign addresses every customer; otherwise it addresses the members of
that group. ``status`` tracks the lifecycle (draft → scheduled → sent); a fresh
campaign starts as ``draft``.

Owner-scoped (SEC-02): every campaign carries the owning merchant's ``user_id`` (and
advisory ``client_id``) so one tenant can neither see another tenant's campaigns nor
target another tenant's group.
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from core.database import Base


class Campaign(Base):
    __tablename__ = "campaigns"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False, index=True)
    # ARC-05: advisory within-tenant narrowing, parity with the core tables.
    client_id = Column(Integer, nullable=True, index=True)
    name = Column(String, nullable=False)
    # Send channel — sms/email; free-form so new channels need no migration.
    channel = Column(String, nullable=False, default="sms")
    message = Column(String, nullable=True)
    # Audience: the customer group this campaign targets, or null ⇒ all customers.
    target_group_id = Column(Integer, nullable=True)
    # Lifecycle: draft → scheduled → sent. Fresh campaigns start as draft.
    status = Column(String, nullable=False, default="draft")

    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
