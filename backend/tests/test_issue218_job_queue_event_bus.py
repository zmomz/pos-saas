"""ISSUE-218 — job queue + internal event bus (M10 / §6.2).

Background work (webhook-delivery retries, ZATCA reconcile, report
materialization, notifications, exports) is funnelled through one
``services.job_queue`` seam, and outbound domain events flow over a real
publish/subscribe ``services.event_bus`` that other services subscribe to.

These tests exercise the default in-process ("memory") backend — the one dev/CI
run — so they assert the *seam and semantics*, not Redis. They pin:

* the queue runs a registered job, retries a failing one with a bounded budget,
  and rejects an unknown job name;
* the event bus fans an event out to subscribers, isolates a failing one, and
  routes outbound webhooks onto the queue;
* the reconcile / materialize / export rails run when enqueued.
"""
import asyncio

import pytest
from sqlalchemy import select

from conftest import add_product, auth_headers, make_client_account
from core.config import settings
from core.database import db_manager
from models.webhooks import Webhooks
from services import event_bus, job_queue
from services.production import WebhookDispatcher


# --------------------------------------------------------------------------- #
# Job queue
# --------------------------------------------------------------------------- #
async def test_enqueue_runs_a_registered_job_inline():
    """Under the memory backend, enqueue executes the job before returning."""
    ran = {}

    @job_queue.job("test.echo")
    async def _echo(*, value):
        ran["value"] = value
        return value

    await job_queue.enqueue("test.echo", value=7)
    assert ran == {"value": 7}


async def test_enqueue_retries_a_transient_failure(monkeypatch):
    """A job that fails then succeeds is retried within the budget (no raise)."""
    monkeypatch.setattr(settings, "job_max_retries", 3, raising=False)
    _real_sleep = asyncio.sleep
    monkeypatch.setattr(asyncio, "sleep", lambda *_a, **_k: _real_sleep(0))
    calls = {"n": 0}

    @job_queue.job("test.flaky")
    async def _flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("transient")
        return "ok"

    await job_queue.enqueue("test.flaky")
    assert calls["n"] == 3  # failed twice, succeeded on the third try


async def test_enqueue_gives_up_after_the_budget_without_propagating(monkeypatch):
    """A perpetually-failing job exhausts retries and is swallowed (best effort)."""
    monkeypatch.setattr(settings, "job_max_retries", 2, raising=False)
    _real_sleep = asyncio.sleep
    monkeypatch.setattr(asyncio, "sleep", lambda *_a, **_k: _real_sleep(0))
    calls = {"n": 0}

    @job_queue.job("test.broken")
    async def _broken():
        calls["n"] += 1
        raise RuntimeError("always")

    await job_queue.enqueue("test.broken")  # must not raise
    assert calls["n"] == 3  # 1 initial + 2 retries


async def test_enqueue_unknown_job_raises():
    with pytest.raises(KeyError):
        await job_queue.enqueue("test.does-not-exist")


# --------------------------------------------------------------------------- #
# Event bus
# --------------------------------------------------------------------------- #
async def test_publish_invokes_subscribers_and_isolates_failures():
    """Every subscriber for an event runs; one raising never blocks the others."""
    seen = []

    async def _good(ctx):
        seen.append(("good", ctx.event, ctx.payload.get("x")))

    async def _bad(ctx):
        raise RuntimeError("subscriber boom")

    event_bus.subscribe("test.evt", _bad)
    event_bus.subscribe("test.evt", _good)
    try:
        async with db_manager.async_session_maker() as db:
            await event_bus.publish(db, "u1", "test.evt", {"x": 42})
        assert ("good", "test.evt", 42) in seen
    finally:
        event_bus.unsubscribe_all()


async def test_wildcard_subscriber_receives_every_event():
    seen = []

    async def _all(ctx):
        seen.append(ctx.event)

    event_bus.subscribe("*", _all)
    try:
        async with db_manager.async_session_maker() as db:
            await event_bus.publish(db, "u1", "alpha", {})
            await event_bus.publish(db, "u1", "beta", {})
        assert seen == ["alpha", "beta"]
    finally:
        event_bus.unsubscribe_all()


async def test_publish_fans_outbound_webhook_onto_the_queue(client, monkeypatch):
    """An event with a subscribed webhook enqueues exactly one delivery, and the
    delivery (HTTP POST + log write) runs on the queue."""
    user, _token, client_id = await make_client_account(client)
    async with db_manager.async_session_maker() as db:
        db.add(Webhooks(
            user_id=user["id"], client_id=client_id, name="hook",
            url="https://example.test/hook", events="product.created",
            secret_key="sek", is_active=True,
        ))
        await db.commit()

    dispatched = []

    async def _record(url, event, payload, secret):
        dispatched.append({"url": url, "event": event})
        return {"status": "delivered", "status_code": 200}

    monkeypatch.setattr(WebhookDispatcher, "dispatch", staticmethod(_record))

    async with db_manager.async_session_maker() as db:
        attempted = await event_bus.publish(db, user["id"], "product.created", {"product_id": 1})

    assert attempted == 1
    assert dispatched == [{"url": "https://example.test/hook", "event": "product.created"}]

    # The delivery job persisted exactly one webhook_deliveries row.
    from models.webhook_deliveries import Webhook_deliveries

    async with db_manager.async_session_maker() as db:
        rows = (
            await db.execute(select(Webhook_deliveries).where(Webhook_deliveries.user_id == user["id"]))
        ).scalars().all()
    assert len(rows) == 1
    assert rows[0].status == "delivered"


# --------------------------------------------------------------------------- #
# Job rails: webhook retry / reconcile / materialize / export
# --------------------------------------------------------------------------- #
async def test_webhook_deliver_job_records_one_failed_row_without_raising(monkeypatch):
    """The webhook.deliver job runs once per enqueue and records exactly one
    delivery row — even on a non-delivered outcome it never raises (so the queue
    does not re-run it and duplicate the row); the retry budget lives inside the
    dispatcher. This pins the ISSUE-029 one-row-per-endpoint invariant."""
    calls = {"n": 0}

    async def _fail(url, event, payload, secret):
        calls["n"] += 1
        return {"status": "failed", "status_code": 500, "error": "HTTP 500"}

    monkeypatch.setattr(WebhookDispatcher, "dispatch", staticmethod(_fail))

    await job_queue.enqueue(
        "webhook.deliver",
        user_id="u_solo", webhook_id=None, url="https://x.test/h",
        event="sale.completed", body={"event": "sale.completed", "data": {}}, secret="s",
    )
    assert calls["n"] == 1  # one job run, no queue-level re-run

    from models.webhook_deliveries import Webhook_deliveries

    async with db_manager.async_session_maker() as db:
        rows = (
            await db.execute(select(Webhook_deliveries).where(Webhook_deliveries.user_id == "u_solo"))
        ).scalars().all()
    assert len(rows) == 1
    assert rows[0].status == "failed"


async def test_reconcile_job_runs_for_a_client(monkeypatch):
    """zatca.reconcile runs the report-pending sweep on the queue."""
    seen = {}

    async def _fake_sweep(db, client_id, **_kw):
        seen["client_id"] = client_id
        return {"processed": 0, "cleared": 0, "reported": 0, "pending": 0, "failed": 0}

    from services import zatca_sale

    monkeypatch.setattr(zatca_sale, "report_pending_documents", _fake_sweep)
    await job_queue.enqueue("zatca.reconcile", client_id=123)
    assert seen == {"client_id": 123}


async def test_materialize_job_runs_for_a_client(client):
    """report.materialize materializes a client's alert feed on the queue.

    A product below the low-stock threshold produces one persisted notification.
    """
    user, _token, client_id = await make_client_account(client)
    await add_product(client_id, user["id"], name="Low", quantity=1, price=5.0)

    await job_queue.enqueue("report.materialize", client_id=client_id, user_id=user["id"])

    from models.notifications import Notifications

    async with db_manager.async_session_maker() as db:
        rows = (
            await db.execute(select(Notifications).where(Notifications.user_id == user["id"]))
        ).scalars().all()
    assert any(r.type == "low_stock" for r in rows)


async def test_export_job_renders_catalog_csv(client):
    """export.generate renders a client's products to CSV off the request path."""
    user, _token, client_id = await make_client_account(client)
    await add_product(client_id, user["id"], name="Bean", quantity=3, price=9.0)

    captured = {}

    # The job returns its summary; run_job surfaces it directly.
    summary = await job_queue.run_job("export.generate", client_id=client_id)
    captured.update(summary)
    assert captured["rows"] == 1
    assert captured["bytes"] > 0
