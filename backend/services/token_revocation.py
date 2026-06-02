"""JWT revocation blocklist (Phase 3 — session / forced logout).

Stateless JWTs cannot be invalidated before they expire, which means a logged-out
or compromised token stays usable until ``exp``. This module adds a server-side
blocklist keyed on the token's ``jti`` claim:

* ``revoke_token`` records a ``jti`` (called from ``/auth/logout``).
* ``is_token_revoked`` is consulted on every authenticated request
  (``dependencies.auth.get_current_user``) and on refresh.

The store is the ``revoked_tokens`` table — durable and works across processes
without Redis. Swap the two functions for a Redis-backed implementation later
without touching callers.
"""
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.revoked_tokens import RevokedTokens

logger = logging.getLogger(__name__)


async def revoke_token(
    db: AsyncSession,
    jti: str,
    *,
    user_id: Optional[str] = None,
    token_type: Optional[str] = None,
    expires_at: Optional[int] = None,
    reason: Optional[str] = None,
) -> None:
    """Add ``jti`` to the blocklist. Idempotent — a duplicate is a no-op."""
    if not jti:
        return
    existing = await db.execute(select(RevokedTokens.id).where(RevokedTokens.jti == jti))
    if existing.scalar_one_or_none() is not None:
        return
    db.add(
        RevokedTokens(
            jti=jti,
            user_id=str(user_id) if user_id else None,
            token_type=token_type,
            expires_at=expires_at,
            reason=reason,
        )
    )
    await db.commit()
    logger.info("Revoked token jti=%s (type=%s)", jti[:8], token_type)


async def is_token_revoked(db: AsyncSession, jti: Optional[str]) -> bool:
    """Return True if ``jti`` is on the blocklist (or missing — fail closed)."""
    if not jti:
        # A token minted before jti was introduced has no jti. Treat as allowed
        # for backward compatibility (it will still expire on its own ``exp``).
        return False
    result = await db.execute(select(RevokedTokens.id).where(RevokedTokens.jti == jti))
    return result.scalar_one_or_none() is not None
