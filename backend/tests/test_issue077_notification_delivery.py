"""ISSUE-077: notification delivery that honors each user's UserProfile prefs.

The notification *center* (models.notifications) persists the in-app feed; this
suite covers delivering those alerts out-of-band over a real channel (email),
gated by the user's saved notification preferences:

  * ``email_alerts``  — the email **channel** master switch (off ⇒ no email).
  * ``low_stock_alerts`` / ``transaction_alerts`` / ``daily_summary`` — per-category
    switches (an alert of that category is delivered only when its switch is on).

Behaviour is exercised through the dispatcher's public interface and, end-to-end,
through the notifications HTTP endpoint that materializes the alert feed.
"""
import pytest

from core.database import db_manager
from services.notifications import NotificationDispatcher
from tests.conftest import add_product, auth_headers, make_client_account, register_user

pytestmark = pytest.mark.asyncio


async def _set_prefs(client, token, **prefs):
    """Persist a partial set of notification toggles for the caller."""
    resp = await client.put(
        "/api/v1/users/preferences",
        headers=auth_headers(token),
        json={"notification_prefs": prefs},
    )
    assert resp.status_code == 200, resp.text


async def test_low_stock_alert_is_emailed_when_channel_and_category_enabled(client, monkeypatch):
    """With defaults (email + low-stock on), a low-stock alert emails the user."""
    user, _token, _ = await register_user(client)

    sent = []

    async def fake_send_email(to_email, subject, body):
        sent.append((to_email, subject, body))
        return True

    monkeypatch.setattr("services.notifications.send_email", fake_send_email)

    async with db_manager.async_session_maker() as db:
        result = await NotificationDispatcher.dispatch(
            db,
            user["id"],
            type="low_stock",
            title="Low Stock Alert",
            message="Widget has only 2 units remaining",
        )

    assert sent == [(user["email"], "Low Stock Alert", "Widget has only 2 units remaining")]
    assert result["email"] == "sent"


async def test_disabled_email_channel_sends_no_email(client, monkeypatch):
    """With the email channel off, the email adapter is never invoked."""
    user, token, _ = await register_user(client)
    await _set_prefs(client, token, email_alerts=False)

    sent = []

    async def fake_send_email(to_email, subject, body):
        sent.append((to_email, subject, body))
        return True

    monkeypatch.setattr("services.notifications.send_email", fake_send_email)

    async with db_manager.async_session_maker() as db:
        result = await NotificationDispatcher.dispatch(
            db,
            user["id"],
            type="low_stock",
            title="Low Stock Alert",
            message="Widget has only 2 units remaining",
        )

    assert sent == []
    assert result["email"] == "skipped"


async def test_disabled_category_suppresses_only_that_category(client, monkeypatch):
    """Email channel on but low-stock category off ⇒ a low-stock alert is skipped,
    while a category without its own toggle (subscription) still rides the channel."""
    user, token, _ = await register_user(client)
    await _set_prefs(client, token, email_alerts=True, low_stock_alerts=False)

    sent = []

    async def fake_send_email(to_email, subject, body):
        sent.append(subject)
        return True

    monkeypatch.setattr("services.notifications.send_email", fake_send_email)

    async with db_manager.async_session_maker() as db:
        low_stock = await NotificationDispatcher.dispatch(
            db, user["id"], type="low_stock", title="Low Stock Alert", message="x"
        )
        subscription = await NotificationDispatcher.dispatch(
            db, user["id"], type="subscription", title="Subscription Payment Due", message="y"
        )

    assert low_stock["email"] == "skipped"
    assert subscription["email"] == "sent"
    assert sent == ["Subscription Payment Due"]


async def test_unsaved_profile_uses_shipped_category_defaults(client, monkeypatch):
    """A user who never saved prefs follows the shipped defaults: low-stock on,
    daily-summary off — so daily-summary is skipped without an explicit toggle."""
    user, _token, _ = await register_user(client)

    sent = []

    async def fake_send_email(to_email, subject, body):
        sent.append(subject)
        return True

    monkeypatch.setattr("services.notifications.send_email", fake_send_email)

    async with db_manager.async_session_maker() as db:
        low_stock = await NotificationDispatcher.dispatch(
            db, user["id"], type="low_stock", title="Low Stock Alert", message="x"
        )
        daily = await NotificationDispatcher.dispatch(
            db, user["id"], type="daily_summary", title="Daily Summary", message="y"
        )

    assert low_stock["email"] == "sent"
    assert daily["email"] == "skipped"
    assert sent == ["Low Stock Alert"]


async def test_new_alert_emails_once_through_notifications_feed(client, monkeypatch):
    """End-to-end: materializing a *new* low-stock alert dispatches one email; a
    refetch (same alert, already materialized) does not re-send."""
    user, token, client_id = await make_client_account(client)
    await add_product(client_id, user["id"], name="Widget", quantity=2)

    sent = []

    async def fake_send_email(to_email, subject, body):
        sent.append((to_email, subject))
        return True

    monkeypatch.setattr("services.notifications.send_email", fake_send_email)

    first = await client.get("/api/v1/notifications/list", headers=auth_headers(token))
    assert first.status_code == 200, first.text
    low_stock_emails = [s for s in sent if s[1] == "Low Stock Alert"]
    assert low_stock_emails == [(user["email"], "Low Stock Alert")]

    # Refetch: the alert already exists (upsert refreshes in place), so no re-send.
    second = await client.get("/api/v1/notifications/list", headers=auth_headers(token))
    assert second.status_code == 200, second.text
    assert [s for s in sent if s[1] == "Low Stock Alert"] == [(user["email"], "Low Stock Alert")]
