"""SEC-15 regression — the cross-cutting throttle sentinels must be Postgres-safe.

SEC-15 keys its per-account and per-IP counters by storing a sentinel in the
"other" key column of the shared ``login_attempts`` table. The original sentinels
carried a NUL byte (``"\\x00account-wide"`` / ``"\\x00ip-wide"``) as a
collision-guard. That works on SQLite — which happily stores NUL inside TEXT — so
the whole suite passed, but **PostgreSQL rejects 0x00 in ``varchar``/``text``**
(``asyncpg``: *invalid byte sequence for encoding "UTF8": 0x00*). On the Postgres
deployment this aborted the transaction on *every* login attempt, surfacing as a
blanket 500 from the auth route.

These tests fail fast on a regression even on SQLite, because they assert on the
*content* of the keys the throttle persists rather than relying on the database
to reject them: a sentinel must contain no NUL byte, yet must stay collision-proof
against a real (validated) email identifier and a real source IP.
"""
import re

from core.config import settings
from core.database import db_manager
from services.login_throttle import (
    _ACCOUNT_IP_SENTINEL,
    _IP_IDENTIFIER_SENTINEL,
    LoginLockedOut,
    assert_login_allowed,
    register_failed_login,
)


def test_sentinels_carry_no_nul_byte():
    # The exact byte Postgres/asyncpg refuse to store in a text column. SQLite
    # tolerates it, so this content check — not the DB — is what guards us.
    for sentinel in (_ACCOUNT_IP_SENTINEL, _IP_IDENTIFIER_SENTINEL):
        assert "\x00" not in sentinel, f"NUL byte in sentinel {sentinel!r} breaks Postgres"


def test_sentinels_are_storable_postgres_text():
    # Postgres text/varchar accepts any UTF-8 *except* NUL. Encoding round-trips
    # cleanly only when there is no embedded 0x00.
    for sentinel in (_ACCOUNT_IP_SENTINEL, _IP_IDENTIFIER_SENTINEL):
        assert b"\x00" not in sentinel.encode("utf-8")


def test_sentinels_stay_collision_proof():
    # Dropping the NUL must not weaken the guarantee that a sentinel can never
    # equal a *real* value: the identifier slot only ever holds a validated email
    # (always contains "@"), and the ip_address slot only ever holds a
    # server-derived request.client.host (a literal IPv4/IPv6 address).
    assert "@" not in _IP_IDENTIFIER_SENTINEL  # cannot be a real email identifier

    ipish = re.compile(r"^[0-9a-fA-F:.]+$")  # any plausible literal IP shape
    assert not ipish.match(_ACCOUNT_IP_SENTINEL)  # cannot be a real client IP


async def test_throttle_round_trips_with_real_email_and_ip(monkeypatch):
    # End-to-end proof the cross-cutting counters work with the sentinels in place:
    # a distributed spray (one failure per IP) trips the per-account lock. On
    # Postgres this exercises the very write path that the NUL byte used to abort.
    monkeypatch.setattr(settings, "login_account_max_attempts", 3, raising=False)
    monkeypatch.setattr(settings, "login_ip_max_attempts", 100, raising=False)

    identifier = "regression@example.com"
    async with db_manager.async_session_maker() as db:
        for i in range(3):
            await register_failed_login(db, identifier, f"192.0.2.{i}")

        locked = False
        try:
            await assert_login_allowed(db, identifier, "192.0.2.250")
        except LoginLockedOut:
            locked = True
        assert locked, "per-account cross-cutting counter failed to lock"
