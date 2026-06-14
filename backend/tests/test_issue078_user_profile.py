"""ISSUE-078: persisted per-user profile + notification preferences.

The profile/notification prefs used to live only in the browser's localStorage,
so they never followed a user to another device and could not drive server-side
notification delivery. These tests exercise the server-side persistence through
the public HTTP interface (``/api/v1/users/preferences``).
"""
import pytest

from tests.conftest import auth_headers, register_user

pytestmark = pytest.mark.asyncio


DEFAULT_PREFS = {
    "email_alerts": True,
    "low_stock_alerts": True,
    "daily_summary": False,
    "transaction_alerts": True,
}


async def test_fresh_user_gets_default_preferences(client):
    """A user who never saved a profile gets sensible server-side defaults."""
    _user, token, _ = await register_user(client)

    resp = await client.get("/api/v1/users/preferences", headers=auth_headers(token))

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["display_name"] is None
    assert body["notification_prefs"] == DEFAULT_PREFS


async def test_saved_preferences_persist_and_reload(client):
    """Saving a profile persists it server-side so a later load returns the values.

    Loading on "another device" is the same user identity issuing a fresh request,
    which the second GET models.
    """
    _user, token, _ = await register_user(client)

    new_prefs = {
        "email_alerts": False,
        "low_stock_alerts": True,
        "daily_summary": True,
        "transaction_alerts": False,
    }
    put = await client.put(
        "/api/v1/users/preferences",
        headers=auth_headers(token),
        json={"display_name": "Front Counter", "notification_prefs": new_prefs},
    )
    assert put.status_code == 200, put.text

    reload = await client.get("/api/v1/users/preferences", headers=auth_headers(token))
    assert reload.status_code == 200, reload.text
    body = reload.json()
    assert body["display_name"] == "Front Counter"
    assert body["notification_prefs"] == new_prefs


async def test_preferences_are_scoped_to_the_user(client):
    """One user's saved profile does not leak into another user's profile."""
    _a, token_a, _ = await register_user(client)
    _b, token_b, _ = await register_user(client)

    saved = await client.put(
        "/api/v1/users/preferences",
        headers=auth_headers(token_a),
        json={"display_name": "User A", "notification_prefs": {"daily_summary": True}},
    )
    assert saved.status_code == 200, saved.text

    other = await client.get("/api/v1/users/preferences", headers=auth_headers(token_b))
    assert other.status_code == 200, other.text
    body = other.json()
    assert body["display_name"] is None
    assert body["notification_prefs"] == DEFAULT_PREFS
