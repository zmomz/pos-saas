from datetime import datetime

from core.database import Base
from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint


class LoginAttempts(Base):
    """Failed-login tracker for brute-force / credential-stuffing protection
    (ISSUE-043).

    One row per (identifier, ip_address). Each failed login bumps ``count`` and
    ``last_attempt_at``; once ``count`` reaches the configured threshold within
    the window, ``locked_until`` is set and further attempts are throttled (429)
    until it passes. A successful login clears the row. Rows are self-healing:
    a failure that lands after the window has elapsed resets the counter.
    """

    __tablename__ = "login_attempts"
    __table_args__ = (
        UniqueConstraint("identifier", "ip_address", name="uq_login_attempts_identifier_ip"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    identifier = Column(String, nullable=False, index=True)
    ip_address = Column(String, nullable=False, default="unknown")
    count = Column(Integer, nullable=False, default=0)
    first_attempt_at = Column(DateTime(timezone=True), default=datetime.now)
    last_attempt_at = Column(DateTime(timezone=True), default=datetime.now)
    # When set and still in the future, logins for this (identifier, ip) are throttled.
    locked_until = Column(DateTime(timezone=True), nullable=True)
