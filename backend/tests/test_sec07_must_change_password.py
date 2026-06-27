"""SEC-07 — enforce the ``must_change_password`` flag.

Provisioning paths (agent/merchant/staff creation) set ``User.must_change_password``
so a first-login user is forced to rotate the temporary credential. The flag was
persisted and surfaced on ``/auth/me`` but never *enforced*: a flagged user kept
full access to every authenticated endpoint, so the forced-rotation gate was a
no-op.

These tests pin the corrected behavior, all driven through the public HTTP API:
- a flagged user is 403'd on a normal protected endpoint;
- the same user may still reach ``/users/change-password`` (and the auth surface)
  so they can actually rotate the credential;
- once the password is changed the flag clears and the *same* token works again;
- an un-flagged user is never affected.
"""
from conftest import auth_headers, register_user, unique_email
from core.database import db_manager
from sqlalchemy import func, update

from models.auth import User

_PW = "Password123"
_NEW_PW = "NewPass456"


async def _flag_and_relogin(client, email: str, password: str = _PW) -> str:
    """Set the DB ``must_change_password`` flag for ``email`` and mint a fresh
    access token (login) that carries the flag in its claims."""
    async with db_manager.async_session_maker() as db:
        await db.execute(
            update(User)
            .where(func.lower(User.email) == email.lower())
            .values(must_change_password=True)
        )
        await db.commit()
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


async def test_flagged_user_blocked_on_protected_endpoint(client):
    email = unique_email()
    await register_user(client, email=email)
    token = await _flag_and_relogin(client, email)

    resp = await client.get("/api/v1/users/profile", headers=auth_headers(token))
    assert resp.status_code == 403, resp.text
    assert "password" in resp.json()["detail"].lower()


async def test_flagged_user_can_reach_change_password(client):
    email = unique_email()
    await register_user(client, email=email)
    token = await _flag_and_relogin(client, email)

    resp = await client.post(
        "/api/v1/users/change-password",
        headers=auth_headers(token),
        json={"current_password": _PW, "new_password": _NEW_PW},
    )
    assert resp.status_code == 200, resp.text


async def test_flag_cleared_after_change_unblocks_same_token(client):
    email = unique_email()
    await register_user(client, email=email)
    token = await _flag_and_relogin(client, email)

    # Pre-change: the protected endpoint is gated.
    blocked = await client.get("/api/v1/users/profile", headers=auth_headers(token))
    assert blocked.status_code == 403, blocked.text

    changed = await client.post(
        "/api/v1/users/change-password",
        headers=auth_headers(token),
        json={"current_password": _PW, "new_password": _NEW_PW},
    )
    assert changed.status_code == 200, changed.text

    # The change clears the DB flag without bumping the security stamp, so the
    # *same* token now passes the gate.
    resp = await client.get("/api/v1/users/profile", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text


async def test_unflagged_user_not_blocked(client):
    _, token, _ = await register_user(client)
    resp = await client.get("/api/v1/users/profile", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text


async def test_flagged_user_can_reach_auth_surface(client):
    email = unique_email()
    await register_user(client, email=email)
    token = await _flag_and_relogin(client, email)

    me = await client.get("/api/v1/auth/me", headers=auth_headers(token))
    assert me.status_code == 200, me.text
    assert me.json()["must_change_password"] is True

    logout = await client.post("/api/v1/auth/logout", headers=auth_headers(token))
    assert logout.status_code == 200, logout.text
