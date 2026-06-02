from datetime import datetime

from core.database import Base
from sqlalchemy import Column, DateTime, Integer, String


class RevokedTokens(Base):
    """Server-side JWT blocklist (Phase 3 — session/forced-logout).

    A row here means the token bearing ``jti`` must be rejected even though its
    signature and ``exp`` are still valid. ``/auth/logout`` inserts a row; every
    authenticated request checks it via ``services.token_revocation``. Rows can be
    purged once ``expires_at`` has passed (the JWT would be rejected on ``exp``
    anyway), but we keep them until then so revocation is authoritative.
    """

    __tablename__ = "revoked_tokens"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    jti = Column(String, nullable=False, unique=True, index=True)
    user_id = Column(String, nullable=True, index=True)
    token_type = Column(String, nullable=True)  # "access" | "refresh"
    # Unix timestamp (seconds) of the token's own expiry — used to prune.
    expires_at = Column(Integer, nullable=True)
    reason = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
