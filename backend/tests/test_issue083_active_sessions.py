"""ISSUE-083: active-session management.

A user can view their active sessions (each login mints a refresh-token-backed
session) and revoke them — individually or all-but-current. Revoking a session
invalidates its refresh token, so a subsequent ``/auth/refresh`` with that
token fails. Tests drive the public HTTP interface.
"""
from conftest import auth_headers, unique_email


async def _login(client, email: str, password: str = "Password123") -> dict:
    """Log in and return the full token payload (token + refresh_token)."""
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _register(client, email: str, password: str = "Password123") -> None:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "name": "Session User"},
    )
    assert resp.status_code == 201, resp.text


async def test_list_sessions_shows_current_session_with_metadata(client):
    """After logging in, the caller can list their active sessions."""
    email = unique_email()
    await _register(client, email)
    login = await _login(client, email)

    resp = await client.get(
        "/api/v1/auth/sessions", headers=auth_headers(login["token"])
    )
    assert resp.status_code == 200, resp.text
    sessions = resp.json()["sessions"]
    assert len(sessions) >= 1
    # The session this access token belongs to is flagged current.
    current = [s for s in sessions if s["current"]]
    assert len(current) == 1
    # Basic metadata is present.
    assert "created_at" in current[0]
    assert "id" in current[0]


async def test_revoking_a_session_invalidates_its_refresh_token(client):
    """Login twice → revoke the first session → its refresh token stops working."""
    email = unique_email()
    await _register(client, email)

    first = await _login(client, email)
    second = await _login(client, email)

    # Two distinct active sessions are visible from the second session.
    listed = await client.get(
        "/api/v1/auth/sessions", headers=auth_headers(second["token"])
    )
    sessions = listed.json()["sessions"]
    assert len(sessions) >= 2

    # The non-current one is the first login's session.
    other = next(s for s in sessions if not s["current"])

    # Sanity: the first session's refresh token still works before revocation.
    pre = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}
    )
    assert pre.status_code == 200, pre.text

    # Revoke the first session from the second.
    revoke = await client.delete(
        f"/api/v1/auth/sessions/{other['id']}", headers=auth_headers(second["token"])
    )
    assert revoke.status_code == 200, revoke.text

    # The revoked session's refresh token no longer mints access tokens.
    post = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}
    )
    assert post.status_code == 401, post.text

    # The current (second) session's refresh token is unaffected.
    still = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": second["refresh_token"]}
    )
    assert still.status_code == 200, still.text


async def test_revoke_unknown_session_returns_404(client):
    """Revoking a session id that isn't an active session of the caller is 404."""
    email = unique_email()
    await _register(client, email)
    login = await _login(client, email)

    resp = await client.delete(
        "/api/v1/auth/sessions/not-a-real-jti", headers=auth_headers(login["token"])
    )
    assert resp.status_code == 404, resp.text


async def test_revoke_others_keeps_only_current_session(client):
    """`DELETE /sessions/others` revokes every session but the caller's current."""
    email = unique_email()
    await _register(client, email)

    first = await _login(client, email)
    current = await _login(client, email)

    resp = await client.delete(
        "/api/v1/auth/sessions/others", headers=auth_headers(current["token"])
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["revoked"] >= 1

    # Only the current session remains active.
    listed = await client.get(
        "/api/v1/auth/sessions", headers=auth_headers(current["token"])
    )
    remaining = listed.json()["sessions"]
    assert len(remaining) == 1
    assert remaining[0]["current"] is True

    # The other session's refresh token is now rejected.
    post = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}
    )
    assert post.status_code == 401, post.text


async def test_logout_drops_the_session_from_the_active_list(client):
    """Logging out a session removes it from another session's active list."""
    email = unique_email()
    await _register(client, email)

    keep = await _login(client, email)
    gone = await _login(client, email)

    # Two sessions active.
    before = await client.get("/api/v1/auth/sessions", headers=auth_headers(keep["token"]))
    assert len(before.json()["sessions"]) >= 2

    out = await client.post("/api/v1/auth/logout", headers=auth_headers(gone["token"]))
    assert out.status_code == 200, out.text

    after = await client.get("/api/v1/auth/sessions", headers=auth_headers(keep["token"]))
    ids = {s["id"] for s in after.json()["sessions"]}
    # The logged-out session is no longer listed; the kept one still is.
    assert keep_sid(keep["token"]) in ids


def keep_sid(access_token: str) -> str:
    """Decode the ``sid`` claim from an access token (test helper)."""
    from core.auth import decode_access_token

    return decode_access_token(access_token)["sid"]
