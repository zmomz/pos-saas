from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String


class Staff_attendance(Base):
    """A single clock-in / clock-out attendance record for a staff member (#216).

    One row per worked session: created on clock-in (``clock_out`` null), closed
    on clock-out. Worked hours are derived from the pair at read time rather than
    stored, so a correction to either timestamp stays consistent.
    """

    __tablename__ = "staff_attendance"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    # The owning merchant's account id — the tenancy boundary (mirrors
    # ``staff_members.user_id``). All attendance is owner-scoped.
    user_id = Column(String, nullable=False, index=True)
    # FK to ``staff_members.id`` (the directory row, not the login).
    staff_id = Column(Integer, nullable=False, index=True)
    branch_id = Column(Integer, nullable=True)
    clock_in = Column(DateTime(timezone=True), nullable=False)
    clock_out = Column(DateTime(timezone=True), nullable=True)
    notes = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
