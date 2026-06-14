from core.database import Base
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Integer, String


class Printers(Base):
    """A merchant's saved/selected printer (H26/U5.2, ISSUE-047).

    Each row is one physical printer the merchant has registered. ``role`` says
    which printables it handles — ``receipt`` (front-of-house customer receipts)
    or ``kot`` (kitchen order tickets) — and an optional ``station_id`` binds a
    KOT printer to a specific prep station so the kitchen ticket for that station
    routes to its own printer. ``is_default`` marks the saved/selected printer the
    routing resolver falls back to for a role when no station-specific match
    exists. ``device_id`` is an opaque client-side handle (a WebUSB device label /
    network address) the browser matches at print time.

    Owner-scoped via ``user_id`` (SEC-02) like every other merchant entity.
    """

    __tablename__ = "printers"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False, index=True)
    client_id = Column(Integer, nullable=True, index=True)
    name = Column(String, nullable=False)
    role = Column(String, nullable=False, default="receipt")  # receipt | kot
    station_id = Column(Integer, nullable=True, index=True)  # prep_stations.id (KOT routing)
    device_id = Column(String, nullable=True)  # client-side WebUSB/network handle
    paper_size = Column(String, nullable=True)  # 80mm | 58mm override
    is_default = Column(Boolean, nullable=True)
    status = Column(String, nullable=False, default="active")  # active | inactive
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
