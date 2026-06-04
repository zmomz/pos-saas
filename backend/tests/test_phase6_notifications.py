"""F-052 — persisted notification center (UX-08).

The notifications page used to synthesize its feed per-request with a no-op
``mark-read`` (read state was a lie across reloads) and a field mismatch that meant
the page never rendered. These tests pin the corrected, persisted behavior:

- a low-stock product surfaces as a persisted notification in the feed;
- a ``mark-read`` acknowledgment *survives a refetch* (the row stays read even
  though the feed is re-materialized on every GET);
- the feed and ``mark-read`` are owner-scoped — a client can neither see nor
  acknowledge another client's notifications (SEC-02).
"""
import pytest
from sqlalchemy import select

from conftest import add_product, auth_headers, make_client_account
from core.database import db_manager
from models.notifications import Notifications


def _low_stock_items(body):
    return [n for n in body["items"] if n["type"] == "low_stock"]


@pytest.mark.asyncio
async def test_low_stock_product_appears_in_persisted_feed(client):
    """A low-stock product surfaces in the feed and is persisted to the table."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await add_product(client_id, user["id"], name="Sugar", quantity=3, price=5.0)

    resp = await client.get("/api/v1/notifications/list", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    low = _low_stock_items(body)
    assert len(low) == 1
    assert "Sugar" in low[0]["message"]
    assert low[0]["is_read"] is False
    assert body["unread_count"] >= 1

    # The notification is persisted (not synthesized in-memory).
    async with db_manager.async_session_maker() as db:
        rows = (
            await db.execute(
                select(Notifications).where(Notifications.user_id == str(user["id"]))
            )
        ).scalars().all()
    assert any(r.type == "low_stock" and "Sugar" in r.message for r in rows)


@pytest.mark.asyncio
async def test_mark_read_survives_refetch(client):
    """Marking a notification read persists across a re-materializing refetch."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await add_product(client_id, user["id"], name="Flour", quantity=2, price=4.0)

    first = (await client.get("/api/v1/notifications/list", headers=headers)).json()
    note = _low_stock_items(first)[0]
    assert note["is_read"] is False

    mark = await client.post(
        "/api/v1/notifications/mark-read",
        json={"notification_id": note["id"]},
        headers=headers,
    )
    assert mark.status_code == 200, mark.text

    # Refetch — the feed is rebuilt every call, but the read flag must stick.
    second = (await client.get("/api/v1/notifications/list", headers=headers)).json()
    same = next(n for n in second["items"] if n["id"] == note["id"])
    assert same["is_read"] is True
    # And it is not double-created on re-materialization (idempotent dedupe_key).
    assert len(_low_stock_items(second)) == 1


@pytest.mark.asyncio
async def test_mark_all_read_persists(client):
    """An empty mark-read marks the caller's whole feed read, persisted."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await add_product(client_id, user["id"], name="Milk", quantity=1, price=3.0)
    await add_product(client_id, user["id"], name="Eggs", quantity=2, price=3.0)

    await client.get("/api/v1/notifications/list", headers=headers)
    resp = await client.post("/api/v1/notifications/mark-read", json={}, headers=headers)
    assert resp.status_code == 200, resp.text

    refetched = (await client.get("/api/v1/notifications/list", headers=headers)).json()
    assert all(n["is_read"] for n in refetched["items"])
    assert refetched["unread_count"] == 0


@pytest.mark.asyncio
async def test_notifications_owner_scoped(client):
    """A client cannot see or acknowledge another client's notifications (SEC-02)."""
    user_a, token_a, client_a = await make_client_account(client)
    headers_a = auth_headers(token_a)
    await add_product(client_a, user_a["id"], name="A-only", quantity=1, price=2.0)
    a_feed = (await client.get("/api/v1/notifications/list", headers=headers_a)).json()
    a_note = _low_stock_items(a_feed)[0]

    _user_b, token_b, _client_b = await make_client_account(client)
    headers_b = auth_headers(token_b)

    # B's feed does not contain A's product alert.
    b_feed = (await client.get("/api/v1/notifications/list", headers=headers_b)).json()
    assert all("A-only" not in n["message"] for n in b_feed["items"])

    # B cannot acknowledge A's notification.
    resp = await client.post(
        "/api/v1/notifications/mark-read",
        json={"notification_id": a_note["id"]},
        headers=headers_b,
    )
    assert resp.status_code == 404, resp.text

    # A's notification is still unread (B's call was rejected, not silently applied).
    a_again = (await client.get("/api/v1/notifications/list", headers=headers_a)).json()
    same = next(n for n in a_again["items"] if n["id"] == a_note["id"])
    assert same["is_read"] is False
