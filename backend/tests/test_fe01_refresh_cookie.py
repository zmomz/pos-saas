"""FE-01 — the refresh token rides an HttpOnly cookie, not just the JSON body.

Storing the refresh token in ``localStorage`` makes it readable by any XSS. The
backend slice of FE-01 issues the refresh token as an HttpOnly / SameSite cookie
on every token-minting endpoint and accepts it from that cookie at ``/refresh``
and ``/logout``, so the SPA never has to persist it in JS-reachable storage.

The body-based ``refresh_token`` path is kept (backward compatible) so existing
callers and the current SPA keep working while the frontend migrates (#146, the
second Ralph iteration). These tests pin only the new cookie behavior.
"""
from conftest import auth_headers, register_user, unique_email

COOKIE = "pos_refresh_token"


def _set_cookie_headers(resp):
    """All raw ``Set-Cookie`` header values on a response (there may be several)."""
    return [v for k, v in resp.headers.multi_items() if k.lower() == "set-cookie"]


def _refresh_set_cookie(resp):
    """The raw ``Set-Cookie`` line that targets the refresh cookie, or None."""
    for line in _set_cookie_headers(resp):
        if line.startswith(f"{COOKIE}="):
            return line
    return None


async def test_login_sets_httponly_refresh_cookie(client):
    email = unique_email()
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123", "name": "A"},
    )
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "Password123"}
    )
    assert resp.status_code == 200, resp.text

    line = _refresh_set_cookie(resp)
    assert line is not None, "login must Set-Cookie the refresh token"
    # The cookie carries the same refresh token returned in the body.
    assert resp.json()["refresh_token"] in line
    # It must be unreadable by JS and scoped to the auth endpoints only.
    assert "HttpOnly" in line
    assert "Path=/api/v1/auth" in line
    assert "SameSite" in line


async def test_register_sets_refresh_cookie(client):
    email = unique_email()
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123", "name": "A"},
    )
    assert resp.status_code == 201, resp.text
    line = _refresh_set_cookie(resp)
    assert line is not None and "HttpOnly" in line


async def test_refresh_works_from_cookie_without_a_body(client):
    # register stores the refresh cookie in the client's jar.
    _, _, _ = await register_user(client)

    # No JSON body at all — the refresh token is read from the cookie.
    resp = await client.post("/api/v1/auth/refresh")
    assert resp.status_code == 200, resp.text
    new_token = resp.json()["token"]

    me = await client.get("/api/v1/auth/me", headers=auth_headers(new_token))
    assert me.status_code == 200


async def test_logout_clears_the_refresh_cookie(client):
    _, token, _ = await register_user(client)

    resp = await client.post("/api/v1/auth/logout", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text

    line = _refresh_set_cookie(resp)
    assert line is not None, "logout must clear the refresh cookie"
    # Cleared cookies are expired immediately (Max-Age=0).
    assert "Max-Age=0" in line
