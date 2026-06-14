from core.database import Base
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Integer, String


class Permissions(Base):
    """A per-user permission override row (``permission_key`` + ``is_granted``).

    These rows are individual grant/deny overrides keyed by ``user_id`` — the
    *role*-driven defaults live in ``dependencies.permissions.ROLE_PERMISSIONS``,
    not on each row, so the old NOT-NULL ``role`` column was redundant and was
    dropped in ISSUE-034 (it was never read by enforcement).
    """

    __tablename__ = "permissions"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False)
    permission_key = Column(String, nullable=False)
    is_granted = Column(Boolean, nullable=False)
    granted_by = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)