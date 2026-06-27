"""Login brute-force protection (ISSUE-043, hardened by SEC-15).

Tracks failed logins in the ``login_attempts`` table and locks out for a
cooldown once a configurable threshold is reached within a rolling window,
mitigating credential-stuffing.

Three counters are maintained, each its own row, so a distributed run can't slip
under the per-pair threshold (SEC-15):

* per (identifier, IP) — the original ISSUE-043 counter.
* per identifier (across all IPs) — locks an account under distributed spray.
* per IP (across all identifiers) — locks a source host spraying many accounts;
  its threshold is higher to limit NAT false positives.

The cross-cutting rows reuse the same table, keyed with a NUL-byte sentinel in
the column they don't scope on (so they can't collide with a real email/IP).
``assert_login_allowed`` blocks if *any* counter is locked; a successful login
clears all three (clearing the IP counter is the NAT-relief path).

Policy knobs (read at call time so they stay configurable / overridable in
tests):

* ``LOGIN_MAX_ATTEMPTS`` — per-pair failures before lockout (default 5).
* ``LOGIN_ACCOUNT_MAX_ATTEMPTS`` — per-account failures before lockout (default 5).
* ``LOGIN_IP_MAX_ATTEMPTS`` — per-IP failures before lockout (default 50).
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
    """Raised when the pair, account, or source IP is currently locked out.

    ``retry_after`` is the number of whole seconds until the lock expires.
    """

    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__(f"Login locked out for {retry_after}s")


# SEC-15: cross-cutting counters live in the same table as the per-pair rows,
# distinguished by a sentinel in the "other" key column. The sentinels carry a
# NUL byte so they can never collide with a real email/identifier or IP address.
_ACCOUNT_IP_SENTINEL = "\x00account-wide"  # ip_address slot of a per-account row
_IP_IDENTIFIER_SENTINEL = "\x00ip-wide"    # identifier slot of a per-IP row


def _max_attempts() -> int:
    try:
        return max(1, int(getattr(settings, "login_max_attempts", 5)))
    except (TypeError, ValueError):
        return 5


def _account_max_attempts() -> int:
    try:
        return max(1, int(getattr(settings, "login_account_max_attempts", 5)))
    except (TypeError, ValueError):
        return 5


def _ip_max_attempts() -> int:
    try:
        return max(1, int(getattr(settings, "login_ip_max_attempts", 50)))
    except (TypeError, ValueError):
        return 50


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


def _row_locked_for(row: Optional[LoginAttempts], now: datetime) -> Optional[int]:
    """Return ``retry_after`` seconds if ``row`` is currently locked, else None."""
    if row is None or row.locked_until is None:
        return None
    locked_until = _as_aware(row.locked_until)
    if locked_until and locked_until > now:
        return int((locked_until - now).total_seconds()) + 1
    return None


async def assert_login_allowed(db: AsyncSession, identifier: str, ip_address: str) -> None:
    """Raise ``LoginLockedOut`` if the pair, the account, or the source IP is locked.

    SEC-15: a lock on *any* of the three counters — the (identifier, IP) pair,
    the account-wide counter, or the IP-wide counter — blocks the attempt.
    """
    identifier = _normalize(identifier)
    ip_address = ip_address or "unknown"
    now = datetime.now(timezone.utc)

    rows = [
        await _get_row(db, identifier, ip_address),
        await _get_row(db, identifier, _ACCOUNT_IP_SENTINEL),
        await _get_row(db, _IP_IDENTIFIER_SENTINEL, ip_address),
    ]
    retry_afters = [r for r in (_row_locked_for(row, now) for row in rows) if r is not None]
    if retry_afters:
        raise LoginLockedOut(max(retry_afters))


async def _bump_failure(
    db: AsyncSession, identifier: str, ip_address: str, threshold: int, now: datetime
) -> None:
    """Increment one counter row, locking it once ``threshold`` is reached.

    Shared by the per-pair, per-account, and per-IP counters — only the key and
    threshold differ. Adds/mutates the row on the session; the caller commits.
    """
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

    if row.count >= threshold:
        row.locked_until = now + timedelta(minutes=_lockout_minutes())
        logger.warning(
            "Login locked out identifier=%s ip=%s after %d failures (threshold=%d)",
            identifier,
            ip_address,
            row.count,
            threshold,
        )


async def register_failed_login(db: AsyncSession, identifier: str, ip_address: str) -> None:
    """Record a failed login against all three counters, locking on any threshold."""
    identifier = _normalize(identifier)
    ip_address = ip_address or "unknown"
    now = datetime.now(timezone.utc)

    await _bump_failure(db, identifier, ip_address, _max_attempts(), now)
    await _bump_failure(db, identifier, _ACCOUNT_IP_SENTINEL, _account_max_attempts(), now)
    await _bump_failure(db, _IP_IDENTIFIER_SENTINEL, ip_address, _ip_max_attempts(), now)

    await db.commit()


async def clear_login_attempts(db: AsyncSession, identifier: str, ip_address: str) -> None:
    """Clear the failure counters after a successful login.

    Drops the pair row, the account-wide row, and the IP-wide row. Clearing the
    IP-wide counter on a *successful* sign-in is the NAT mitigation: a legitimate
    user behind a shared IP relieves pressure that would otherwise lock the host.
    """
    identifier = _normalize(identifier)
    ip_address = ip_address or "unknown"
    for ident, ip in (
        (identifier, ip_address),
        (identifier, _ACCOUNT_IP_SENTINEL),
        (_IP_IDENTIFIER_SENTINEL, ip_address),
    ):
        row = await _get_row(db, ident, ip)
        if row is not None:
            await db.delete(row)
    await db.commit()
