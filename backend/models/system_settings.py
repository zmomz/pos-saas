from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String


class System_settings(Base):
    """Platform-wide key/value settings owned by the master tier.

    Used for settings that are global to the whole platform rather than scoped to
    a single tenant — e.g. the global VAT rate that agents inherit and cannot
    override (SRS MA-05). One row per ``key``.
    """

    __tablename__ = "system_settings"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    key = Column(String, nullable=False, unique=True, index=True)
    value = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
