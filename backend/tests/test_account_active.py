"""Suspended-client (is_active=False) enforcement tests."""
from conftest import auth_headers, make_client_account


async def test_active_client_can_authenticate(client):
    _, token, _ = await make_client_account(client, is_active=True)
    resp = await client.get("/api/v1/auth/me", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text


async def test_suspended_client_is_blocked(client):
    _, token, _ = await make_client_account(client, is_active=False)
    resp = await client.get("/api/v1/auth/me", headers=auth_headers(token))
    assert resp.status_code == 403, resp.text
    assert "suspended" in resp.json()["detail"].lower()
