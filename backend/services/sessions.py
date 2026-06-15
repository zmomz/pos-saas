"""Active-session registry + revocation (ISSUE-083).

Refresh tokens are stateless JWTs; on their own they can be listed only if we
record them. Each login registers a :class:`UserSession` keyed on the refresh
token's ``jti``. This module is the single place that:

* records a session (``record_session``),
* lists a user's *active* sessions for the management UI (``list_active_sessions``),
* revokes a session — individually or all-but-current — which both stamps
  ``revoked_at`` and adds the ``jti`` to the shared revocation blocklist so the
  session's refresh token is rejected at ``/auth/refresh`` (``revoke_session`` /
  ``revoke_other_sessions``),
* records a session's most-recent use (``touch_session``).

Revocation goes through ``services.token_revocation`` so the existing
``/auth/refresh`` revocation check enforces it with no extra wiring.
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional

from models.user_sessions import UserSession
from services.token_revocation import revoke_token
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def record_session(
    db: AsyncSession,
    *,
    user_id: str,
    jti: str,
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None,
    expires_at: Optional[int] = None,
) -> None:
    """Register a freshly issued refresh token as an active session."""
    if not jti:
        return
    db.add(
        UserSession(
            user_id=str(user_id),
            jti=jti,
            user_agent=user_agent,
            ip_address=ip_address,
            expires_at=expires_at,
        )
    )
    await db.commit()
    logger.info("Recorded session jti=%s for user", jti[:8])


async def list_active_sessions(db: AsyncSession, user_id: str) -> List[UserSession]:
    """Return a user's active (non-revoked) sessions, newest first."""
    result = await db.execute(
        select(UserSession)
        .where(UserSession.user_id == str(user_id), UserSession.revoked_at.is_(None))
        .order_by(UserSession.created_at.desc())
    )
    return list(result.scalars().all())


async def touch_session(db: AsyncSession, jti: Optional[str]) -> None:
    """Stamp a session's ``last_used_at`` when its refresh token is exchanged."""
    if not jti:
        return
    result = await db.execute(select(UserSession).where(UserSession.jti == jti))
    session = result.scalar_one_or_none()
    if session is None:
        return
    session.last_used_at = datetime.now(timezone.utc)
    await db.commit()


async def revoke_session(db: AsyncSession, user_id: str, jti: str) -> bool:
    """Revoke one of ``user_id``'s sessions by its ``jti``.

    Stamps ``revoked_at`` and blocklists the ``jti`` so the session's refresh
    token can no longer mint access tokens. Returns ``False`` if no active
    session with that ``jti`` belongs to the user (callers surface a 404).
    """
    result = await db.execute(
        select(UserSession).where(
            UserSession.jti == jti,
            UserSession.user_id == str(user_id),
            UserSession.revoked_at.is_(None),
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        return False
    session.revoked_at = datetime.now(timezone.utc)
    await db.commit()
    await revoke_token(
        db, jti, user_id=user_id, token_type="refresh", expires_at=session.expires_at, reason="session_revoked"
    )
    return True


async def revoke_other_sessions(db: AsyncSession, user_id: str, keep_jti: Optional[str]) -> int:
    """Revoke all of ``user_id``'s active sessions except ``keep_jti``.

    Returns the number of sessions revoked.
    """
    sessions = await list_active_sessions(db, user_id)
    revoked = 0
    for session in sessions:
        if session.jti == keep_jti:
            continue
        if await revoke_session(db, user_id, session.jti):
            revoked += 1
    return revoked
