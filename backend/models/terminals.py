"""Integrated payment terminals — paired in-store SoftPOS devices (HW-03/PAY-05, F-005).

A merchant registers the SoftPOS terminal(s) they have paired (today: Geidea), so a
card-like tender at checkout can be pushed to a specific device for a real approval
(``POST /api/v1/payments/terminal/charge {terminal_id, amount}``, IB §4.6). This is
the ``terminals`` entity the payments family was missing (deferred from F-003 to
this finding).

Every row carries ``user_id`` (the merchant's own login account) so the service
layer scopes reads/writes to the owner exactly like every other entity — one client
can never charge another client's terminal (SEC-02).

* ``provider`` : the terminal SDK/acquirer — ``geidea`` (the wired in-store option).
* ``serial``   : the device serial Geidea pairs the capture to (no card data here).
* ``status``   : ``active`` (usable) / ``inactive`` (decommissioned).
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from core.database import Base


class Terminals(Base):
    __tablename__ = "terminals"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False, index=True)
    client_id = Column(Integer, nullable=True, index=True)
    branch_id = Column(Integer, nullable=True)
    # geidea (the wired in-store SoftPOS provider); pax/urovo/ngenius slot in later.
    provider = Column(String, nullable=False, default="geidea", server_default="geidea")
    label = Column(String, nullable=True)
    # The paired device serial Geidea routes the capture to (never card data).
    serial = Column(String, nullable=True)
    # active / inactive
    status = Column(String, nullable=False, default="active", server_default="active")
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
