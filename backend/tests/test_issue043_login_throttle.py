"""ISSUE-043 — login brute-force protection.

Repeated failed logins for an identifier are throttled/locked after a
configurable number of failures, mitigating credential-stuffing. A legitimate
login after the lock window succeeds, and a success before the threshold clears
the running failure count.
"""
from datetime import datetime, timedelta, timezone

from conftest import register_user, unique_email
from core.database import db_manager
from models.login_attempts import LoginAttempts
from sqlalchemy import select


async def test_repeated_failed_logins_are_locked_out(client):
    email = unique_email()
    await register_user(client, email=email, password="Password123")

    # The first N failures return 401 (bad credentials) — default policy is 5.
    for _ in range(5):
        bad = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": "WrongPass1"}
        )
        assert bad.status_code == 401, bad.text

    # The next attempt is throttled regardless of the password supplied.
    locked = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "WrongPass1"}
    )
    assert locked.status_code == 429, locked.text


async def test_correct_password_is_rejected_while_locked(client):
    email = unique_email()
    await register_user(client, email=email, password="Password123")

    for _ in range(5):
        await client.post("/api/v1/auth/login", json={"email": email, "password": "WrongPass1"})

    # Even the right password is refused while the lock holds, and the response
    # advertises when to retry.
    blocked = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "Password123"}
    )
    assert blocked.status_code == 429, blocked.text
    assert int(blocked.headers["retry-after"]) > 0


async def test_successful_login_resets_failure_counter(client):
    email = unique_email()
    await register_user(client, email=email, password="Password123")

    # Four failures — one short of the lockout threshold.
    for _ in range(4):
        await client.post("/api/v1/auth/login", json={"email": email, "password": "WrongPass1"})

    # A correct login still succeeds and clears the running count.
    ok = await client.post("/api/v1/auth/login", json={"email": email, "password": "Password123"})
    assert ok.status_code == 200, ok.text

    # Four more failures must not lock out: if the counter hadn't reset, the
    # cumulative total (8) would already exceed the threshold.
    for _ in range(4):
        again = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": "WrongPass1"}
        )
        assert again.status_code == 401, again.text


async def test_legitimate_login_succeeds_after_lock_expires(client):
    email = unique_email()
    await register_user(client, email=email, password="Password123")

    for _ in range(5):
        await client.post("/api/v1/auth/login", json={"email": email, "password": "WrongPass1"})

    # Locked now.
    locked = await client.post("/api/v1/auth/login", json={"email": email, "password": "Password123"})
    assert locked.status_code == 429

    # Fast-forward past the lockout window by aging every stored lock for this
    # account. SEC-15 keeps both a per-(identifier, IP) counter and a per-account
    # counter, so the threshold trips more than one row — age them all.
    async with db_manager.async_session_maker() as db:
        rows = (
            await db.execute(select(LoginAttempts).where(LoginAttempts.identifier == email.lower()))
        ).scalars().all()
        for row in rows:
            row.locked_until = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db.commit()

    # The legitimate user can sign in again.
    ok = await client.post("/api/v1/auth/login", json={"email": email, "password": "Password123"})
    assert ok.status_code == 200, ok.text


async def test_lockout_threshold_is_configurable(client, monkeypatch):
    from core.config import settings

    monkeypatch.setattr(settings, "login_max_attempts", 3, raising=False)

    email = unique_email()
    await register_user(client, email=email, password="Password123")

    # With the threshold lowered to 3, three failures lock the pair out.
    for _ in range(3):
        bad = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": "WrongPass1"}
        )
        assert bad.status_code == 401, bad.text

    locked = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "WrongPass1"}
    )
    assert locked.status_code == 429, locked.text
