"""F-046 — omnichannel Salla connector (OMN-01..03).

The omnichannel family was entirely absent: a merchant could not sell online and
have those orders land on the POS / decrement the shared stock. These tests pin the
first connector:

- a sample Salla order webhook **materializes a POS transaction and decrements the
  same shared stock** (the catch-forever contract test, OMN-03);
- re-delivery of the same webhook is idempotent (never double-books);
- an unknown store / a disabled ``omnichannel`` feature is ignored (no sale);
- a configured webhook secret enforces HMAC signature verification (OMN-01);
- the imported orders list is owner-scoped (SEC-02).
"""
import hashlib
import hmac
import json
import uuid

import pytest
from sqlalchemy import select

from conftest import auth_headers, make_client_account
from core.database import db_manager
from models.channel_orders import Channel_orders
from models.client_features import Client_features
from models.products import Products
from models.transactions import Transactions
from services.omnichannel import verify_salla_signature


def test_verify_salla_signature_rejects_non_ascii_without_raising():
    # A non-ASCII signature header must fail closed (False -> 401), not raise
    # TypeError inside hmac.compare_digest (-> 500). A real hex digest is ASCII.
    assert verify_salla_signature("secret", b"{}", "deadbeefé") is False


async def _add_product_with_barcode(client_id, user_id, *, barcode, name="T-Shirt", quantity=10, price=100.0):
    async with db_manager.async_session_maker() as db:
        product = Products(
            user_id=user_id,
            client_id=client_id,
            name=name,
            barcode=barcode,
            price=price,
            quantity=quantity,
            is_active=True,
        )
        db.add(product)
        await db.commit()
        await db.refresh(product)
        return product.id


async def _product_qty(product_id):
    async with db_manager.async_session_maker() as db:
        return (
            await db.execute(select(Products.quantity).where(Products.id == product_id))
        ).scalar_one()


def _salla_payload(*, merchant, order_id, sku, qty, price=100.0):
    return {
        "event": "order.created",
        "merchant": merchant,
        "data": {
            "id": order_id,
            "reference_id": 41027,
            "customer": {"first_name": "Sara", "last_name": "Ali", "mobile": "+966500000000"},
            "total": {"amount": price * qty, "currency": "SAR"},
            "items": [
                {
                    "sku": sku,
                    "name": "T-Shirt",
                    "quantity": qty,
                    "amounts": {"price_without_tax": {"amount": price, "currency": "SAR"}},
                }
            ],
        },
    }


# A configured webhook secret is now mandatory for a webhook to be accepted
# (SEC-09: the connector fails closed when no secret is set), so the helpers default
# to connecting WITH a secret and signing every post. Tests that exercise the
# unsigned / no-secret paths pass ``secret=None`` explicitly.
_WEBHOOK_SECRET = "whsec_omni_default"


async def _connect(client, headers, store_id, secret=_WEBHOOK_SECRET):
    body = {"store_id": store_id}
    if secret is not None:
        body["webhook_secret"] = secret
    resp = await client.post("/api/v1/omnichannel/salla/connect", json=body, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _post_webhook(client, payload, secret=_WEBHOOK_SECRET):
    """POST a Salla webhook, HMAC-signing the raw body when a secret is given."""
    raw = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if secret is not None:
        headers["X-Salla-Signature"] = hmac.new(
            secret.encode("utf-8"), raw, hashlib.sha256
        ).hexdigest()
    return await client.post("/api/v1/omnichannel/salla/webhook", content=raw, headers=headers)


@pytest.mark.asyncio
async def test_salla_webhook_materializes_transaction_and_decrements_stock(client):
    """A sample Salla order webhook → a real POS sale + the shared stock decrements."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    store_id = f"store_{uuid.uuid4().hex[:8]}"
    sku = f"SKU-{uuid.uuid4().hex[:6]}"
    pid = await _add_product_with_barcode(client_id, user["id"], barcode=sku, quantity=10)
    await _connect(client, headers, store_id)

    payload = _salla_payload(merchant=store_id, order_id=90001, sku=sku, qty=2)
    resp = await _post_webhook(client, payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "imported"
    assert body["transaction_id"] is not None

    # Shared stock decremented by the ordered quantity (OMN-03).
    assert await _product_qty(pid) == 8

    # The order now appears in the back-office transaction history (it is a real sale).
    txns = await client.get("/api/v1/pos/transactions", headers=headers)
    assert txns.status_code == 200
    assert any(t["id"] == body["transaction_id"] for t in txns.json()["items"])

    # A durable channel-order record links the Salla order to the materialized sale.
    listing = await client.get("/api/v1/omnichannel/channel-orders", headers=headers)
    assert listing.status_code == 200
    rows = listing.json()["items"]
    assert len(rows) == 1
    assert rows[0]["external_order_id"] == "90001"
    assert rows[0]["transaction_id"] == body["transaction_id"]
    assert rows[0]["status"] == "imported"


@pytest.mark.asyncio
async def test_salla_webhook_is_idempotent(client):
    """Re-delivery of the same order never double-books a sale or double-decrements."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    store_id = f"store_{uuid.uuid4().hex[:8]}"
    sku = f"SKU-{uuid.uuid4().hex[:6]}"
    pid = await _add_product_with_barcode(client_id, user["id"], barcode=sku, quantity=10)
    await _connect(client, headers, store_id)

    payload = _salla_payload(merchant=store_id, order_id=90002, sku=sku, qty=3)
    first = (await _post_webhook(client, payload)).json()
    second = (await _post_webhook(client, payload)).json()

    assert first["status"] == "imported"
    assert second["status"] == "duplicate"
    assert second["transaction_id"] == first["transaction_id"]

    # Stock decremented exactly once.
    assert await _product_qty(pid) == 7
    async with db_manager.async_session_maker() as db:
        rows = (
            await db.execute(
                select(Channel_orders).where(Channel_orders.client_id == client_id)
            )
        ).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_salla_webhook_unknown_store_ignored(client):
    """A webhook for a store no client connected is acked but materializes nothing."""
    resp = await client.post(
        "/api/v1/omnichannel/salla/webhook",
        json=_salla_payload(merchant="not_connected_store", order_id=1, sku="X", qty=1),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ignored"


@pytest.mark.asyncio
async def test_salla_webhook_signature_enforced_when_secret_set(client):
    """With a webhook secret configured, a missing/bad signature is rejected (401)."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    store_id = f"store_{uuid.uuid4().hex[:8]}"
    sku = f"SKU-{uuid.uuid4().hex[:6]}"
    pid = await _add_product_with_barcode(client_id, user["id"], barcode=sku, quantity=10)
    secret = "whsec_test_123"
    await _connect(client, headers, store_id, secret=secret)

    payload = _salla_payload(merchant=store_id, order_id=90003, sku=sku, qty=1)
    raw = json.dumps(payload).encode("utf-8")

    # No signature → rejected, nothing changes.
    bad = await client.post(
        "/api/v1/omnichannel/salla/webhook",
        content=raw,
        headers={"Content-Type": "application/json"},
    )
    assert bad.status_code == 401, bad.text
    assert await _product_qty(pid) == 10

    # Valid HMAC-SHA256 signature → accepted.
    sig = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    good = await client.post(
        "/api/v1/omnichannel/salla/webhook",
        content=raw,
        headers={"Content-Type": "application/json", "X-Salla-Signature": sig},
    )
    assert good.status_code == 200, good.text
    assert good.json()["status"] == "imported"
    assert await _product_qty(pid) == 9


@pytest.mark.asyncio
async def test_salla_webhook_rejected_when_no_secret_configured(client):
    """Fail closed (SEC-09): a store connected WITHOUT a webhook secret rejects every
    webhook with 401. Previously the connector fell open when no secret was set, so an
    unauthenticated caller could book sales just by guessing the (routable) store id."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    store_id = f"store_{uuid.uuid4().hex[:8]}"
    sku = f"SKU-{uuid.uuid4().hex[:6]}"
    pid = await _add_product_with_barcode(client_id, user["id"], barcode=sku, quantity=10)
    await _connect(client, headers, store_id, secret=None)

    resp = await client.post(
        "/api/v1/omnichannel/salla/webhook",
        json=_salla_payload(merchant=store_id, order_id=90008, sku=sku, qty=2),
    )
    assert resp.status_code == 401, resp.text
    # Nothing materialized — the shared stock is untouched.
    assert await _product_qty(pid) == 10


@pytest.mark.asyncio
async def test_disabled_omnichannel_feature_ignores_webhook(client):
    """When the agent disabled the omnichannel feature, the webhook materializes nothing."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    store_id = f"store_{uuid.uuid4().hex[:8]}"
    sku = f"SKU-{uuid.uuid4().hex[:6]}"
    pid = await _add_product_with_barcode(client_id, user["id"], barcode=sku, quantity=10)
    await _connect(client, headers, store_id)

    # Agent disables the omnichannel feature for this client.
    async with db_manager.async_session_maker() as db:
        db.add(
            Client_features(
                user_id=user["id"],
                client_id=client_id,
                feature_name="omnichannel",
                is_enabled=False,
            )
        )
        await db.commit()

    resp = await _post_webhook(
        client, _salla_payload(merchant=store_id, order_id=90004, sku=sku, qty=2)
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "feature_disabled"
    assert await _product_qty(pid) == 10


@pytest.mark.asyncio
async def test_channel_orders_listing_is_owner_scoped(client):
    """One client never sees another client's imported online orders (SEC-02)."""
    user_a, token_a, client_a = await make_client_account(client)
    headers_a = auth_headers(token_a)
    store_a = f"store_{uuid.uuid4().hex[:8]}"
    sku_a = f"SKU-{uuid.uuid4().hex[:6]}"
    await _add_product_with_barcode(client_a, user_a["id"], barcode=sku_a, quantity=10)
    await _connect(client, headers_a, store_a)
    await _post_webhook(
        client, _salla_payload(merchant=store_a, order_id=90005, sku=sku_a, qty=1)
    )

    # A second, unrelated client lists their own channel orders — sees none of A's.
    _user_b, token_b, _client_b = await make_client_account(client)
    headers_b = auth_headers(token_b)
    listing_b = await client.get("/api/v1/omnichannel/channel-orders", headers=headers_b)
    assert listing_b.status_code == 200
    assert listing_b.json()["total"] == 0


async def _txn_items(transaction_id):
    async with db_manager.async_session_maker() as db:
        items_json = (
            await db.execute(
                select(Transactions.items_json).where(Transactions.id == transaction_id)
            )
        ).scalar_one()
    return json.loads(items_json) if items_json else []


@pytest.mark.asyncio
async def test_salla_fractional_line_quantity_preserved(client):
    """A weighted/fractional Salla line keeps its float qty (INV-01) — no int() truncation.

    Previously the Salla connector ``int()``-ed the line quantity, so a 1.5 kg line
    rang up as 1 unit and only decremented one unit of stock — diverging from the
    aggregator connector (which keeps float). Pin the float all the way through.
    """
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    store_id = f"store_{uuid.uuid4().hex[:8]}"
    sku = f"SKU-{uuid.uuid4().hex[:6]}"
    pid = await _add_product_with_barcode(client_id, user["id"], barcode=sku, quantity=10)
    await _connect(client, headers, store_id)

    payload = _salla_payload(merchant=store_id, order_id=90006, sku=sku, qty=1.5)
    resp = await _post_webhook(client, payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "imported"

    # The materialized sale line carries the fractional quantity verbatim.
    items = await _txn_items(body["transaction_id"])
    assert len(items) == 1
    assert items[0]["quantity"] == 1.5

    # Shared stock decremented by the fractional amount (10 - 1.5).
    assert await _product_qty(pid) == 8.5


@pytest.mark.asyncio
async def test_salla_zero_quantity_line_skipped(client):
    """A zero-quantity Salla line is dropped (no sale line, no decrement)."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    store_id = f"store_{uuid.uuid4().hex[:8]}"
    sku = f"SKU-{uuid.uuid4().hex[:6]}"
    pid = await _add_product_with_barcode(client_id, user["id"], barcode=sku, quantity=10)
    await _connect(client, headers, store_id)

    payload = _salla_payload(merchant=store_id, order_id=90007, sku=sku, qty=0)
    resp = await _post_webhook(client, payload)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "no_lines"

    # No line rang up → stock untouched.
    assert await _product_qty(pid) == 10
