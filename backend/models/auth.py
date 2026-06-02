from models.base import Base
from sqlalchemy import Column, DateTime, String
from sqlalchemy.sql import func


class User(Base):
    __tablename__ = "users"

    id = Column(String(255), primary_key=True, index=True)  # UUID generated on registration
    email = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=True)
    hashed_password = Column(String(255), nullable=True)  # bcrypt hash; null for legacy/SSO accounts
    role = Column(String(50), default="user", nullable=False)  # user/admin
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login = Column(DateTime(timezone=True), nullable=True)
