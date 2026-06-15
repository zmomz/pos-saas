"""ISSUE-082: password reset / forgot-password.

A user who forgot their password requests a reset, receives a time-limited
single-use token (delivered out-of-band over the email channel), and exchanges
it for a new password. Tests drive the public HTTP interface.

The reset token is delivered by email in production; in dev/no-SMTP mode the
``/password/forgot`` response surfaces it so the flow is testable end-to-end
(mirrors how provisioning surfaces a temp password in dev).
"""
from datetime import datetime, timedelta, timezone

from conftest import auth_headers, register_user, unique_email


async def _request_reset(client, email: str) -> str:
    """Request a reset for ``email`` and return the surfaced dev token."""
    resp = await client.post("/api/v1/auth/password/forgot", json={"email": email})
    assert resp.status_code == 200, resp.text
    return resp.json().get("reset_token")


async def test_forgot_password_issues_reset_token(client):
    """Requesting a reset for a real account returns 200 and a reset token (dev)."""
    email = unique_email()
    await register_user(client, email=email, password="Password123")

    resp = await client.post("/api/v1/auth/password/forgot", json={"email": email})
    assert resp.status_code == 200, resp.text
    # In dev/no-SMTP the token is surfaced so the flow can be completed/tested.
    assert resp.json().get("reset_token")


async def test_reset_round_trip_logs_in_with_new_password(client):
    """request → reset → the new password works and the old one is rejected."""
    email = unique_email()
    await register_user(client, email=email, password="OldPassword123")
    token = await _request_reset(client, email)

    reset = await client.post(
        "/api/v1/auth/password/reset",
        json={"token": token, "new_password": "BrandNew456"},
    )
    assert reset.status_code == 200, reset.text

    # New password logs in.
    ok = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "BrandNew456"}
    )
    assert ok.status_code == 200, ok.text
    assert ok.json().get("token")

    # Old password no longer works.
    bad = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "OldPassword123"}
    )
    assert bad.status_code == 401


async def test_reset_token_is_single_use(client):
    """A token works exactly once; replaying it is rejected with 400."""
    email = unique_email()
    await register_user(client, email=email, password="Password123")
    token = await _request_reset(client, email)

    first = await client.post(
        "/api/v1/auth/password/reset", json={"token": token, "new_password": "FirstNew123"}
    )
    assert first.status_code == 200, first.text

    second = await client.post(
        "/api/v1/auth/password/reset", json={"token": token, "new_password": "SecondNew123"}
    )
    assert second.status_code == 400


async def test_expired_reset_token_is_rejected(client):
    """A token past its expiry is rejected (time-limited)."""
    from sqlalchemy import update

    from core.database import db_manager
    from models.password_reset import PasswordResetToken
    from services.password_reset import _hash_token

    email = unique_email()
    await register_user(client, email=email, password="Password123")
    token = await _request_reset(client, email)

    # Age the token: force its expiry into the past.
    async with db_manager.async_session_maker() as db:
        await db.execute(
            update(PasswordResetToken)
            .where(PasswordResetToken.token_hash == _hash_token(token))
            .values(expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
        )
        await db.commit()

    resp = await client.post(
        "/api/v1/auth/password/reset", json={"token": token, "new_password": "TooLate123"}
    )
    assert resp.status_code == 400


async def test_forgot_password_unknown_email_does_not_enumerate(client):
    """An unknown address still returns 200 but mints no token (no enumeration)."""
    resp = await client.post(
        "/api/v1/auth/password/forgot", json={"email": unique_email()}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json().get("reset_token") is None


async def test_reset_drops_previously_issued_sessions(client):
    """Policy: a reset invalidates the user's outstanding access + refresh tokens."""
    email = unique_email()
    _, access, refresh = await register_user(client, email=email, password="Password123")

    # The session works before the reset.
    me = await client.get("/api/v1/auth/me", headers=auth_headers(access))
    assert me.status_code == 200

    token = await _request_reset(client, email)
    reset = await client.post(
        "/api/v1/auth/password/reset", json={"token": token, "new_password": "BrandNew456"}
    )
    assert reset.status_code == 200, reset.text

    # The old access token no longer authenticates.
    me_after = await client.get("/api/v1/auth/me", headers=auth_headers(access))
    assert me_after.status_code == 401

    # The old refresh token can no longer mint a new access token.
    refreshed = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert refreshed.status_code == 401
