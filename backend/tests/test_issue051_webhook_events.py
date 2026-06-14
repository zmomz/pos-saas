"""ISSUE-051 — every advertised webhook event fires at its source.

The WebhookManagement UI advertises nine events but, before this slice, only
``sale.completed`` and ``refund.created`` were ever dispatched — and the refund
name didn't even match the UI's ``sale.refunded``. Subscribers to
product/customer/shift/inventory events silently received nothing.

These tests pin one behaviour per advertised event: register a webhook
subscribed to the event, perform the originating action through the public HTTP
API, and assert the dispatcher saw exactly that event (deliveries persist via
ISSUE-029). ``WebhookDispatcher.dispatch`` is stubbed so nothing hits the wire.
"""
from sqlalchemy import select

from conftest import add_product, auth_headers, make_client_account
from core.database import db_manager
from models.webhooks import Webhooks
from services.production import WebhookDispatcher


async def _add_hook(user_id, *, events, client_id=None, url="https://example.test/hook"):
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


def _capture(monkeypatch):
    """Stub the dispatcher, returning the list it appends each fired event to."""
    fired: list = []

    async def _record(url, event, payload, secret):
        fired.append({"url": url, "event": event, "payload": payload})
        return {"status": "delivered", "status_code": 200}

    monkeypatch.setattr(WebhookDispatcher, "dispatch", staticmethod(_record))
    return fired


async def _set_vat(client_id, vat="300000000000003"):
    from models.clients import Clients

    async with db_manager.async_session_maker() as db:
        row = (await db.execute(select(Clients).where(Clients.id == client_id))).scalar_one()
        row.vat_number = vat
        await db.commit()


async def _sale(client, headers, pid, *, qty=2):
    resp = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Cola", "price": 10.0, "quantity": qty}],
            "payment_method": "cash",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_refund_fires_sale_refunded_not_refund_created(client, monkeypatch):
    """A refund dispatches ``sale.refunded`` — the name the UI advertises."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _set_vat(client_id)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=10, price=10.0)
    await _add_hook(user["id"], events="sale.refunded", client_id=client_id)

    fired = _capture(monkeypatch)
    sale = await _sale(client, headers, pid)
    resp = await client.post(
        f"/api/v1/pos/transactions/{sale['id']}/refund", headers=headers
    )
    assert resp.status_code == 200, resp.text

    events = [f["event"] for f in fired]
    assert "sale.refunded" in events
    assert "refund.created" not in events


async def test_creating_a_product_fires_product_created(client, monkeypatch):
    """Creating a product dispatches ``product.created`` to a subscriber."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _add_hook(user["id"], events="product.created", client_id=client_id)

    fired = _capture(monkeypatch)
    resp = await client.post(
        "/api/v1/entities/products",
        json={"client_id": client_id, "name": "Latte", "price": 12.0, "quantity": 5},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    pid = resp.json()["id"]

    created = [f for f in fired if f["event"] == "product.created"]
    assert len(created) == 1
    assert created[0]["payload"]["data"]["product_id"] == pid


async def test_updating_a_product_fires_product_updated(client, monkeypatch):
    """Updating a product dispatches ``product.updated`` to a subscriber."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Mocha", quantity=5, price=15.0)
    await _add_hook(user["id"], events="product.updated", client_id=client_id)

    fired = _capture(monkeypatch)
    resp = await client.put(
        f"/api/v1/entities/products/{pid}",
        json={"price": 18.0},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    updated = [f for f in fired if f["event"] == "product.updated"]
    assert len(updated) == 1
    assert updated[0]["payload"]["data"]["product_id"] == pid


async def test_creating_a_customer_fires_customer_created(client, monkeypatch):
    """Creating a customer dispatches ``customer.created`` to a subscriber."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _add_hook(user["id"], events="customer.created", client_id=client_id)

    fired = _capture(monkeypatch)
    resp = await client.post(
        "/api/v1/entities/customers",
        json={"name": "Aisha", "phone": "0500000000"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    cid = resp.json()["id"]

    created = [f for f in fired if f["event"] == "customer.created"]
    assert len(created) == 1
    assert created[0]["payload"]["data"]["customer_id"] == cid


async def test_opening_a_shift_fires_shift_opened(client, monkeypatch):
    """Opening a shift dispatches ``shift.opened`` to a subscriber."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _add_hook(user["id"], events="shift.opened", client_id=client_id)

    fired = _capture(monkeypatch)
    resp = await client.post(
        "/api/v1/production/shifts/open",
        json={"opening_cash": 100.0},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    shift_id = resp.json()["id"]

    opened = [f for f in fired if f["event"] == "shift.opened"]
    assert len(opened) == 1
    assert opened[0]["payload"]["data"]["shift_id"] == shift_id


async def test_closing_a_shift_fires_shift_closed(client, monkeypatch):
    """Closing a shift dispatches ``shift.closed`` to a subscriber."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _add_hook(user["id"], events="shift.closed", client_id=client_id)

    open_resp = await client.post(
        "/api/v1/production/shifts/open",
        json={"opening_cash": 100.0},
        headers=headers,
    )
    assert open_resp.status_code == 200, open_resp.text
    shift_id = open_resp.json()["id"]

    fired = _capture(monkeypatch)
    close_resp = await client.post(
        "/api/v1/production/shifts/close",
        json={"closing_cash": 100.0},
        headers=headers,
    )
    assert close_resp.status_code == 200, close_resp.text

    closed = [f for f in fired if f["event"] == "shift.closed"]
    assert len(closed) == 1
    assert closed[0]["payload"]["data"]["shift_id"] == shift_id


async def test_stock_adjustment_fires_inventory_updated(client, monkeypatch):
    """A stock count/adjustment dispatches ``inventory.updated`` to a subscriber."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Beans", quantity=20, price=8.0)
    await _add_hook(user["id"], events="inventory.updated", client_id=client_id)

    fired = _capture(monkeypatch)
    resp = await client.post(
        "/api/v1/production/stock-adjustments",
        json={"product_id": pid, "reason": "count", "counted_quantity": 17},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    updated = [f for f in fired if f["event"] == "inventory.updated"]
    assert len(updated) == 1
    data = updated[0]["payload"]["data"]
    assert data["product_id"] == pid
    assert data["counted_quantity"] == 17


async def test_sale_dropping_stock_to_threshold_fires_product_low_stock(client, monkeypatch):
    """A sale that drops a product to/below the low-stock threshold dispatches
    ``product.low_stock`` to a subscriber."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _set_vat(client_id)
    # Threshold default is 10; start at 11 and sell 2 → 9 ≤ 10 triggers the alert.
    pid = await add_product(client_id, user["id"], name="Cola", quantity=11, price=10.0)
    await _add_hook(user["id"], events="product.low_stock", client_id=client_id)

    fired = _capture(monkeypatch)
    await _sale(client, headers, pid, qty=2)

    low = [f for f in fired if f["event"] == "product.low_stock"]
    assert len(low) == 1
    assert low[0]["payload"]["data"]["product_id"] == pid
