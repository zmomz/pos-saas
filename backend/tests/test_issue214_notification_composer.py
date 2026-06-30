"""ISSUE-214 (M10 / parity #8): the operator notification composer + channel prefs.

Covers the ``POST /api/v1/production/notifications/send`` composer — channel
selection (email / WhatsApp / push), scheduling, and validation — plus the
persistence of the new WhatsApp/push channel preferences on the user profile.

The composer is honest about delivery state: email reports ``sent`` only when the
transport delivered (we stub it), WhatsApp/push report ``logged`` until a
provider is wired, and a future ``scheduled_at`` reports ``scheduled`` without
delivering now.
"""
import pytest

from tests.conftest import auth_headers, register_user

pytestmark = pytest.mark.asyncio

SEND_URL = "/api/v1/production/notifications/send"


async def test_email_notification_is_composed_and_sent(client, monkeypatch):
    """An email composed via the endpoint is delivered over the email transport."""
    _user, token, _ = await register_user(client)

    sent = []

    async def fake_send_email(to_email, subject, body):
        sent.append((to_email, subject, body))
        return True

    # EmailService.send_email imports core.email.send_email at call time.
    monkeypatch.setattr("core.email.send_email", fake_send_email)

    resp = await client.post(
        SEND_URL,
        headers=auth_headers(token),
        json={
            "channel": "email",
            "to": "buyer@example.com",
            "subject": "Receipt",
            "body": "Thanks for your purchase",
        },
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["channel"] == "email"
    assert data["status"] == "sent"
    assert sent == [("buyer@example.com", "Receipt", "Thanks for your purchase")]


async def test_legacy_to_email_field_still_works(client, monkeypatch):
    """Pre-composer callers that send ``to_email`` keep working."""
    _user, token, _ = await register_user(client)

    async def fake_send_email(to_email, subject, body):
        return False  # dev fallback

    monkeypatch.setattr("core.email.send_email", fake_send_email)

    resp = await client.post(
        SEND_URL,
        headers=auth_headers(token),
        json={"to_email": "legacy@example.com", "subject": "Hi", "body": "Hello"},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "logged"  # transport reported dev fallback
    assert data["to"] == "legacy@example.com"


async def test_whatsapp_channel_reports_logged_without_provider(client):
    """WhatsApp has no provider wired — it logs and reports ``logged``, never sent."""
    _user, token, _ = await register_user(client)

    resp = await client.post(
        SEND_URL,
        headers=auth_headers(token),
        json={"channel": "whatsapp", "to": "+966500000000", "body": "Order ready"},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["channel"] == "whatsapp"
    assert data["status"] == "logged"
    assert data["delivered"] is False


async def test_push_channel_reports_logged_without_provider(client):
    """Push has no provider wired — it logs and reports ``logged``."""
    _user, token, _ = await register_user(client)

    resp = await client.post(
        SEND_URL,
        headers=auth_headers(token),
        json={"channel": "push", "to": "device-token", "body": "You have a new order"},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "logged"


async def test_scheduled_notification_is_deferred_not_sent(client, monkeypatch):
    """A future ``scheduled_at`` is acknowledged as scheduled and not delivered now."""
    _user, token, _ = await register_user(client)

    sent = []

    async def fake_send_email(to_email, subject, body):
        sent.append((to_email, subject, body))
        return True

    monkeypatch.setattr("core.email.send_email", fake_send_email)

    resp = await client.post(
        SEND_URL,
        headers=auth_headers(token),
        json={
            "channel": "email",
            "to": "buyer@example.com",
            "subject": "Reminder",
            "body": "Your reservation is tomorrow",
            "scheduled_at": "2099-01-01T09:00:00Z",
        },
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "scheduled"
    assert data["scheduled_at"].startswith("2099-01-01")
    assert sent == []  # nothing delivered now


async def test_unknown_channel_is_rejected(client):
    """An unsupported channel is a 400, not a silent no-op."""
    _user, token, _ = await register_user(client)

    resp = await client.post(
        SEND_URL,
        headers=auth_headers(token),
        json={"channel": "carrier_pigeon", "to": "x", "body": "hi"},
    )
    assert resp.status_code == 400


async def test_missing_recipient_is_rejected(client):
    """A composed notification with no recipient is a 400."""
    _user, token, _ = await register_user(client)

    resp = await client.post(
        SEND_URL,
        headers=auth_headers(token),
        json={"channel": "email", "body": "no recipient"},
    )
    assert resp.status_code == 400


async def test_channel_prefs_persist(client):
    """The new WhatsApp/push channel toggles round-trip through the profile API."""
    _user, token, _ = await register_user(client)

    # Defaults: new channels off.
    resp = await client.get("/api/v1/users/preferences", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    prefs = resp.json()["notification_prefs"]
    assert prefs["whatsapp_alerts"] is False
    assert prefs["push_alerts"] is False

    # Enable them and confirm they persist.
    resp = await client.put(
        "/api/v1/users/preferences",
        headers=auth_headers(token),
        json={"notification_prefs": {"whatsapp_alerts": True, "push_alerts": True}},
    )
    assert resp.status_code == 200, resp.text

    resp = await client.get("/api/v1/users/preferences", headers=auth_headers(token))
    prefs = resp.json()["notification_prefs"]
    assert prefs["whatsapp_alerts"] is True
    assert prefs["push_alerts"] is True
