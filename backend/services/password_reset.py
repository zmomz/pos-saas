"""Password-reset (forgot-password) service — ISSUE-082.

Owns the lifecycle of the single-use, time-limited reset grant:

* ``request_reset`` mints a random token for an account, stores only its SHA-256
  hash, and delivers the plaintext out-of-band over the email channel.
* ``reset`` validates a presented token (unused + unexpired), sets the new
  password, burns the token, and bumps the user's security stamp so previously
  issued access/refresh tokens stop working (old sessions are dropped).

To avoid leaking which emails have accounts, ``request_reset`` is silent for an
unknown address — the router responds 200 either way.
"""
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from core.config import settings
from core.email import send_email
from core.security import hash_password
from models.auth import User
from models.password_reset import PasswordResetToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

DEFAULT_TTL_MINUTES = 30


def _hash_token(token: str) -> str:
    """SHA-256 hex of a reset token (what we persist; the plaintext is emailed)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _as_utc(dt: datetime) -> datetime:
    """Treat a stored datetime as UTC. SQLite hands back naive datetimes, so
    normalize before comparing against an aware ``now`` to avoid a TypeError."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _ttl_minutes() -> int:
    try:
        return int(getattr(settings, "password_reset_ttl_minutes", DEFAULT_TTL_MINUTES))
    except (TypeError, ValueError):
        return DEFAULT_TTL_MINUTES


class PasswordResetService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def request_reset(self, email: str) -> Optional[str]:
        """Issue a reset token for ``email`` and email it. Returns the plaintext.

        Returns ``None`` (and does nothing) when no account matches the address,
        so the caller can respond identically for known and unknown emails.
        """
        result = await self.db.execute(
            select(User).where(User.email == (email or "").strip().lower())
        )
        user = result.scalar_one_or_none()
        if user is None:
            return None

        token = secrets.token_urlsafe(32)
        self.db.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=_hash_token(token),
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=_ttl_minutes()),
            )
        )
        await self.db.commit()

        await send_email(
            user.email,
            "Reset your password",
            (
                "We received a request to reset your password.\n\n"
                f"Your reset code is:\n\n  {token}\n\n"
                f"It expires in {_ttl_minutes()} minutes. If you did not request "
                "this, you can ignore this email — your password is unchanged.\n"
            ),
        )
        return token

    async def reset(self, token: str, new_password: str) -> bool:
        """Consume ``token`` and set the account's password to ``new_password``.

        Returns ``False`` when the token is unknown, already used, or expired —
        the caller maps that to a 400. On success the token is burned (single
        use) and the new password takes effect.
        """
        result = await self.db.execute(
            select(PasswordResetToken).where(
                PasswordResetToken.token_hash == _hash_token(token or "")
            )
        )
        grant = result.scalar_one_or_none()
        if grant is None or grant.used_at is not None:
            return False
        if grant.expires_at is not None and _as_utc(grant.expires_at) <= datetime.now(timezone.utc):
            return False

        user = (
            await self.db.execute(select(User).where(User.id == grant.user_id))
        ).scalar_one_or_none()
        if user is None:
            return False

        user.hashed_password = hash_password(new_password)
        # First reset also clears any forced-reset flag (first-login flow).
        if getattr(user, "must_change_password", False):
            user.must_change_password = False
        # Bump the security stamp so tokens issued before this reset stop working
        # (drops previously issued sessions — see dependencies.auth/get_current_user).
        user.token_version = int(getattr(user, "token_version", 0) or 0) + 1
        grant.used_at = datetime.now(timezone.utc)
        await self.db.commit()
        logger.info("Password reset completed for user %s", user.id)
        return True
