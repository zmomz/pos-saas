from models.base import Base
from sqlalchemy import Boolean, Column, DateTime, String, Text
from sqlalchemy.sql import func


class UserMfa(Base):
    """Per-user TOTP multi-factor state (ISSUE-081).

    A row is created when a user begins enrollment (``enabled=False`` with a
    pending ``secret``) and flipped to ``enabled=True`` once a code is verified.
    ``recovery_codes`` holds a JSON list of ``{"hash": <bcrypt>, "used": bool}``
    so single-use backup codes can be checked without storing them in the clear.
    """

    __tablename__ = "user_mfa"
    __table_args__ = {"extend_existing": True}

    user_id = Column(String(255), primary_key=True, index=True)
    secret = Column(String(64), nullable=True)  # base32 TOTP shared secret
    enabled = Column(Boolean, nullable=False, default=False, server_default="false")
    recovery_codes = Column(Text, nullable=True)  # JSON: [{"hash": ..., "used": false}]
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
