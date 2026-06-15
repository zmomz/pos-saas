from datetime import datetime

from models.base import Base
from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.sql import func


class UserSession(Base):
    """A user's authenticated session, one per issued refresh token (ISSUE-083).

    Each login mints a refresh token whose ``jti`` is recorded here so the user
    can *see* their active sessions and revoke them individually or all-but-the
    -current one. ``jti`` doubles as the session identifier and as the key added
    to the revocation blocklist when a session is revoked — so a revoked
    session's refresh token can no longer mint access tokens at ``/auth/refresh``.

    A session is *active* while ``revoked_at`` is ``NULL``. Metadata (user agent,
    IP) is captured at login for the management UI; it is advisory only.
    """

    __tablename__ = "user_sessions"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String(255), nullable=False, index=True)
    # The refresh token's ``jti`` — also the session identifier used to revoke.
    jti = Column(String, nullable=False, unique=True, index=True)
    user_agent = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)
    # Unix timestamp (seconds) of the refresh token's own expiry.
    expires_at = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), default=datetime.now)
    # Bumped to "now" each time this session's refresh token is exchanged.
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    # Set when the session is revoked (logout / explicit revoke). NULL => active.
    revoked_at = Column(DateTime(timezone=True), nullable=True)
