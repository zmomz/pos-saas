from models.base import Base
from sqlalchemy import Boolean, Column, DateTime, String
from sqlalchemy.sql import func


class User(Base):
    __tablename__ = "users"

    id = Column(String(255), primary_key=True, index=True)  # UUID generated on registration
    email = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=True)
    hashed_password = Column(String(255), nullable=True)  # bcrypt hash; null for legacy/SSO accounts
    role = Column(String(50), default="user", nullable=False)  # user/admin
    # Set True when an account is provisioned with a generated temp password
    # (agents/clients created by master/agent). Cleared on first password change.
    # Drives the frontend force-reset-on-first-login screen.
    must_change_password = Column(Boolean, nullable=False, default=False, server_default="false")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login = Column(DateTime(timezone=True), nullable=True)
