"""ISSUE-029 — webhook delivery logs.

Each webhook dispatch is persisted to ``webhook_deliveries`` (event, target,
status, timestamp, response) so the WebhookManagement "Delivery Logs" tab and
its "Deliveries Today" stat render real history instead of a swallowed 404.

Covers:
* a fired event persists one delivery row per attempted endpoint [AC1/AC4];
* ``GET /production/webhooks/logs`` returns the persisted rows, joined to the
  webhook name and carrying success/status_code for the tab [AC2/AC3];
* the log feed is owner-scoped — a merchant never sees another's deliveries [AC2].
"""
from sqlalchemy import select

from conftest import auth_headers, make_client_account
from core.database import db_manager
from models.webhooks import Webhooks
from services.production import WebhookDispatcher, fire_event


async def _add_hook(user_id, *, url, events="sale.completed", client_id=None):
    async with db_manager.async_session_maker() as db:
        hook = Webhooks(
            user_id=user_id,
            client_id=client_id,
            name="hook",
            url=url,
            events=events,
            secret_key="sek",
            is_active=True,
        )
        db.add(hook)
        await db.commit()
        await db.refresh(hook)
        return hook.id


async def test_fire_event_persists_delivery_row(client, monkeypatch):
    """A fired event records one webhook_deliveries row per attempted endpoint."""
    user, _token, client_id = await make_client_account(client)
    await _add_hook(user["id"], url="https://example.test/hook", client_id=client_id)

    async def _record(url, event, payload, secret):
        return {"status": "delivered", "status_code": 200, "response_time_ms": 12}

    monkeypatch.setattr(WebhookDispatcher, "dispatch", staticmethod(_record))

    async with db_manager.async_session_maker() as db:
        attempted = await fire_event(db, user["id"], "sale.completed", {"x": 1})
    assert attempted == 1

    from models.webhook_deliveries import Webhook_deliveries

    async with db_manager.async_session_maker() as db:
        rows = (
            await db.execute(
                select(Webhook_deliveries).where(Webhook_deliveries.user_id == user["id"])
            )
        ).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.event == "sale.completed"
    assert row.target_url == "https://example.test/hook"
    assert row.status == "delivered"
    assert row.status_code == 200
    assert row.created_at is not None


async def test_logs_endpoint_returns_persisted_rows(client, monkeypatch):
    """GET /webhooks/logs returns rows joined to the webhook name + success flag."""
    user, token, client_id = await make_client_account(client)
    await _add_hook(user["id"], url="https://example.test/hook", client_id=client_id)

    async def _record(url, event, payload, secret):
        return {"status": "delivered", "status_code": 200, "response_time_ms": 7}

    monkeypatch.setattr(WebhookDispatcher, "dispatch", staticmethod(_record))
    async with db_manager.async_session_maker() as db:
        await fire_event(db, user["id"], "sale.completed", {"x": 1})

    resp = await client.get(
        "/api/v1/production/webhooks/logs", headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 1
    log = body["items"][0]
    assert log["event"] == "sale.completed"
    assert log["webhook_name"] == "hook"
    assert log["success"] is True
    assert log["status_code"] == 200
    assert log["response_time_ms"] == 7
    assert log["created_at"]


async def test_logs_endpoint_is_owner_scoped(client, monkeypatch):
    """A merchant never sees another merchant's webhook deliveries."""
    owner_a, _ta, ca = await make_client_account(client)
    owner_b, token_b, cb = await make_client_account(client)
    await _add_hook(owner_a["id"], url="https://a.test/hook", client_id=ca)
    await _add_hook(owner_b["id"], url="https://b.test/hook", client_id=cb)

    async def _record(url, event, payload, secret):
        return {"status": "delivered", "status_code": 200}

    monkeypatch.setattr(WebhookDispatcher, "dispatch", staticmethod(_record))
    async with db_manager.async_session_maker() as db:
        await fire_event(db, owner_a["id"], "sale.completed", {"x": 1})

    # Owner B fired nothing → sees no rows, not owner A's.
    resp = await client.get(
        "/api/v1/production/webhooks/logs", headers=auth_headers(token_b)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 0
    assert body["items"] == []
