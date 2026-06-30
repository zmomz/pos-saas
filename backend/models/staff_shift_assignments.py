from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String


class Staff_shift_assignments(Base):
    """A scheduled shift assigned to a staff member (#216).

    Distinct from ``shifts`` (the cash-drawer register session): this is the
    *roster* — who is rostered to work when. ``starts_at`` / ``ends_at`` are the
    planned window; attendance (``staff_attendance``) records the actual clock
    in/out against it.
    """

    __tablename__ = "staff_shift_assignments"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    # Owning merchant's account id — the tenancy boundary.
    user_id = Column(String, nullable=False, index=True)
    staff_id = Column(Integer, nullable=False, index=True)
    branch_id = Column(Integer, nullable=True)
    starts_at = Column(DateTime(timezone=True), nullable=False)
    ends_at = Column(DateTime(timezone=True), nullable=False)
    role = Column(String, nullable=True)
    notes = Column(String, nullable=True)
    # scheduled | cancelled
    status = Column(String, nullable=False, default="scheduled", server_default="scheduled")
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
