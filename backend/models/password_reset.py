from models.base import Base
from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.sql import func


class PasswordResetToken(Base):
    """A single-use, time-limited password-reset grant (ISSUE-082).

    The plaintext token is delivered to the user out-of-band (email channel) and
    never stored: only its SHA-256 ``token_hash`` is persisted, so a database
    read cannot mint a reset. A token is spent by stamping ``used_at`` (single
    use) and is rejected once ``expires_at`` has passed.
    """

    __tablename__ = "password_reset_tokens"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(255), index=True, nullable=False)
    token_hash = Column(String(64), unique=True, index=True, nullable=False)  # sha256 hex
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
