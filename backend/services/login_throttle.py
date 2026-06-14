"""Login brute-force protection (ISSUE-043).

Tracks failed logins per (identifier, IP) in the ``login_attempts`` table and
locks the pair out for a cooldown once a configurable threshold is reached
within a rolling window, mitigating credential-stuffing.

Policy knobs (read at call time so they stay configurable / overridable in
tests):

* ``LOGIN_MAX_ATTEMPTS`` — failures before lockout (default 5).
* ``LOGIN_LOCKOUT_MINUTES`` — how long the lock holds (default 15).
* ``LOGIN_ATTEMPT_WINDOW_MINUTES`` — failures older than this don't count;
  a fresh failure after the window resets the counter (default 15).

Callers: ``routers/auth.login`` checks ``assert_login_allowed`` before
authenticating, records a failure with ``register_failed_login`` on bad
credentials, and clears the row with ``clear_login_attempts`` on success.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from core.config import settings
from models.login_attempts import LoginAttempts
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class LoginLockedOut(Exception):
    """Raised when an (identifier, IP) is currently locked out.

    ``retry_after`` is the number of whole seconds until the lock expires.
    """

    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__(f"Login locked out for {retry_after}s")


def _max_attempts() -> int:
    try:
        return max(1, int(getattr(settings, "login_max_attempts", 5)))
    except (TypeError, ValueError):
        return 5


def _lockout_minutes() -> int:
    try:
        return max(0, int(getattr(settings, "login_lockout_minutes", 15)))
    except (TypeError, ValueError):
        return 15


def _window_minutes() -> int:
    try:
        return max(0, int(getattr(settings, "login_attempt_window_minutes", 15)))
    except (TypeError, ValueError):
        return 15


def _normalize(identifier: str) -> str:
    return (identifier or "").strip().lower()


def _as_aware(value: Optional[datetime]) -> Optional[datetime]:
    """SQLite round-trips naive datetimes; treat stored values as UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


async def _get_row(db: AsyncSession, identifier: str, ip_address: str) -> Optional[LoginAttempts]:
    result = await db.execute(
        select(LoginAttempts).where(
            LoginAttempts.identifier == identifier,
            LoginAttempts.ip_address == ip_address,
        )
    )
    return result.scalar_one_or_none()


async def assert_login_allowed(db: AsyncSession, identifier: str, ip_address: str) -> None:
    """Raise ``LoginLockedOut`` if this (identifier, IP) is currently locked."""
    row = await _get_row(db, _normalize(identifier), ip_address or "unknown")
    if row is None or row.locked_until is None:
        return
    now = datetime.now(timezone.utc)
    locked_until = _as_aware(row.locked_until)
    if locked_until and locked_until > now:
        retry_after = int((locked_until - now).total_seconds()) + 1
        raise LoginLockedOut(retry_after)


async def register_failed_login(db: AsyncSession, identifier: str, ip_address: str) -> None:
    """Record a failed login, locking the pair out once the threshold is hit."""
    identifier = _normalize(identifier)
    ip_address = ip_address or "unknown"
    now = datetime.now(timezone.utc)

    row = await _get_row(db, identifier, ip_address)
    if row is None:
        row = LoginAttempts(
            identifier=identifier,
            ip_address=ip_address,
            count=0,
            first_attempt_at=now,
            last_attempt_at=now,
        )
        db.add(row)

    # A failure that lands after the window has elapsed starts a fresh count.
    window = _window_minutes()
    last = _as_aware(row.last_attempt_at)
    if window and last and (now - last) > timedelta(minutes=window):
        row.count = 0
        row.first_attempt_at = now
        row.locked_until = None

    row.count = (row.count or 0) + 1
    row.last_attempt_at = now

    if row.count >= _max_attempts():
        row.locked_until = now + timedelta(minutes=_lockout_minutes())
        logger.warning(
            "Login locked out identifier=%s ip=%s after %d failures",
            identifier,
            ip_address,
            row.count,
        )

    await db.commit()


async def clear_login_attempts(db: AsyncSession, identifier: str, ip_address: str) -> None:
    """Clear the failure counter after a successful login."""
    row = await _get_row(db, _normalize(identifier), ip_address or "unknown")
    if row is not None:
        await db.delete(row)
        await db.commit()
