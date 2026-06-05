"""F-060 — Aggregator ingest (Deliverect-class middleware webhook).

Delivery-aggregator orders (Jahez / HungerStation) reach the POS **only** through a
Deliverect / Delivery-Hero-POS-partner middleware webhook (the SRS forbids direct
aggregator APIs). A single ingested order both:

1. materializes a **tableless order ticket fired to the KDS** (F-057/F-058), so the
   kitchen prepares it like any order, and
2. books a **real ZATCA sale via the shared sale core** (slice 06) that decrements
   the **same shared stock** — identical compliance to an in-store POS sale.

Ingest is **idempotent** on ``(provider, external_order_id, client_id)`` via the
existing ``channel_orders`` table: webhook re-delivery never double-books a ticket or
a sale. An invalid HMAC signature is rejected.

The named catch-forever test required by the slice is
``test_deliverect_webhook_creates_ticket_and_sale_idempotent``.
"""
import hashlib
import hmac
import json
import uuid

import pytest
from sqlalchemy import func, select

from conftest import add_product, auth_headers, get_product_quantity, make_client_account
from core.database import db_manager
from models.channel_orders import Channel_orders
from models.clients import Clients
from models.transactions import Transactions
from models.zatca_documents import ZatcaDocuments


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _set_vat(client_id: int, vat: str = "300000000000003"):
    async with db_manager.async_session_maker() as db:
        row = (await db.execute(select(Clients).where(Clients.id == client_id))).scalar_one()
        row.vat_number = vat
        await db.commit()


async def _restaurant_client(client):
    """A restaurant client with a VAT number so the settled sale can be ZATCA-signed."""
    user, token, client_id = await make_client_account(client, business_type="restaurant")
    await _set_vat(client_id)
    return user, token, client_id


async def _connect(client, headers, location, secret=None):
    body = {"location_id": location}
    if secret is not None:
        body["webhook_secret"] = secret
    resp = await client.post("/api/v1/aggregator/connect", json=body, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _deliverect_payload(*, location, order_id, name="Burger", plu=None, qty=2, price=20.0, order_type="delivery"):
    item = {"name": name, "quantity": qty, "price": price}
    if plu:
        item["plu"] = plu
    return {
        "location": location,
        "channelOrderId": order_id,
        "channelOrderDisplayId": "JZ-1001",
        "channel": "jahez",
        "orderType": order_type,
        "customer": {"name": "Aggregator Customer", "phoneNumber": "+966500000000"},
        "items": [item],
        "payment": {"amount": price * qty},
    }


async def _txn_count(client_id: int) -> int:
    async with db_manager.async_session_maker() as db:
        return (
            await db.execute(
                select(func.count(Transactions.id)).where(Transactions.client_id == client_id)
            )
        ).scalar() or 0


async def _doc_count(client_id: int) -> int:
    async with db_manager.async_session_maker() as db:
        return (
            await db.execute(
                select(func.count(ZatcaDocuments.id)).where(ZatcaDocuments.client_id == client_id)
            )
        ).scalar() or 0


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_deliverect_webhook_creates_ticket_and_sale_idempotent(client):
    """The catch-forever contract: a valid order → a fired KDS ticket + a ZATCA sale
    that decrements shared stock, and re-delivery never double-books."""
    user, token, client_id = await _restaurant_client(client)
    headers = auth_headers(token)
    location = f"loc_{uuid.uuid4().hex[:8]}"
    pid = await add_product(client_id, user["id"], name="Burger", quantity=10, price=20.0)
    await _connect(client, headers, location)

    payload = _deliverect_payload(location=location, order_id="DLVR-9001", name="Burger", qty=2)
    resp = await client.post("/api/v1/aggregator/deliverect/webhook", json=payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "imported"
    assert body["ticket_id"] is not None
    assert body["transaction_id"] is not None

    # 1) The order fired to the KDS — an active card exists for the materialized ticket.
    kds = await client.get("/api/v1/restaurant/kds/tickets", headers=headers)
    assert kds.status_code == 200
    cards = kds.json()["items"]
    assert len(cards) == 1
    card = cards[0]
    assert card["order_ticket_id"] == body["ticket_id"]
    assert card["order_type"] == "delivery"
    assert card["status"] == "active"
    # A kitchen card never carries money.
    assert all("price" not in it for it in card["items"])

    # 2) The same order booked a real ZATCA sale that decremented the shared stock.
    assert await get_product_quantity(pid) == 8
    assert await _txn_count(client_id) == 1
    assert await _doc_count(client_id) == 1  # ECDSA-stamped fiscal document

    # 3) A durable channel-order record links the aggregator order to the sale.
    listing = await client.get("/api/v1/omnichannel/channel-orders", headers=headers)
    assert listing.status_code == 200
    rows = listing.json()["items"]
    assert len(rows) == 1
    assert rows[0]["provider"] == "deliverect"
    assert rows[0]["external_order_id"] == "DLVR-9001"
    assert rows[0]["transaction_id"] == body["transaction_id"]

    # 4) Idempotent: re-delivering the SAME webhook books nothing new.
    again = await client.post("/api/v1/aggregator/deliverect/webhook", json=payload)
    assert again.status_code == 200, again.text
    assert again.json()["status"] == "duplicate"
    assert again.json()["transaction_id"] == body["transaction_id"]

    # No second ticket, sale, or channel-order; stock untouched by the replay.
    assert await get_product_quantity(pid) == 8
    assert await _txn_count(client_id) == 1
    async with db_manager.async_session_maker() as db:
        n_channel = (
            await db.execute(
                select(func.count(Channel_orders.id)).where(Channel_orders.client_id == client_id)
            )
        ).scalar()
    assert n_channel == 1


@pytest.mark.asyncio
async def test_invalid_signature_rejected(client):
    """With a webhook secret configured, a missing/bad signature is rejected (401)
    and nothing is materialized; a valid HMAC-SHA256 is accepted."""
    user, token, client_id = await _restaurant_client(client)
    headers = auth_headers(token)
    location = f"loc_{uuid.uuid4().hex[:8]}"
    pid = await add_product(client_id, user["id"], name="Pizza", quantity=10, price=30.0)
    secret = "whsec_aggr_123"
    await _connect(client, headers, location, secret=secret)

    payload = _deliverect_payload(location=location, order_id="DLVR-9002", name="Pizza", qty=1, price=30.0)
    raw = json.dumps(payload).encode("utf-8")

    # No signature → rejected, nothing changes.
    bad = await client.post(
        "/api/v1/aggregator/deliverect/webhook",
        content=raw,
        headers={"Content-Type": "application/json"},
    )
    assert bad.status_code == 401, bad.text
    assert await get_product_quantity(pid) == 10
    assert await _txn_count(client_id) == 0

    # Valid HMAC-SHA256 signature → accepted, sale booked.
    sig = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    good = await client.post(
        "/api/v1/aggregator/deliverect/webhook",
        content=raw,
        headers={"Content-Type": "application/json", "X-Webhook-Signature": sig},
    )
    assert good.status_code == 200, good.text
    assert good.json()["status"] == "imported"
    assert await get_product_quantity(pid) == 9


@pytest.mark.asyncio
async def test_unknown_location_and_provider(client):
    """A webhook for an unconnected location is acked-but-ignored; an unknown
    provider is a 404 (no silent ingest)."""
    # Unknown location — acked so the middleware stops retrying.
    resp = await client.post(
        "/api/v1/aggregator/deliverect/webhook",
        json=_deliverect_payload(location="not_connected", order_id="X", qty=1),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ignored"

    # Unknown provider in the path → 404.
    bad = await client.post(
        "/api/v1/aggregator/talabat/webhook",
        json=_deliverect_payload(location="whatever", order_id="Y", qty=1),
    )
    assert bad.status_code == 404, bad.text


@pytest.mark.asyncio
async def test_delivery_hero_provider_routes_separately(client):
    """The provider is recorded per webhook path, and the same external id under two
    providers is two distinct orders (the idempotency key includes provider)."""
    user, token, client_id = await _restaurant_client(client)
    headers = auth_headers(token)
    location = f"loc_{uuid.uuid4().hex[:8]}"
    await add_product(client_id, user["id"], name="Wrap", quantity=50, price=15.0)
    await _connect(client, headers, location)

    shared_id = "ORDER-77"
    a = await client.post(
        "/api/v1/aggregator/deliverect/webhook",
        json=_deliverect_payload(location=location, order_id=shared_id, name="Wrap", qty=1, price=15.0),
    )
    b = await client.post(
        "/api/v1/aggregator/delivery_hero/webhook",
        json=_deliverect_payload(location=location, order_id=shared_id, name="Wrap", qty=1, price=15.0),
    )
    assert a.json()["status"] == "imported"
    assert b.json()["status"] == "imported"
    assert a.json()["transaction_id"] != b.json()["transaction_id"]

    listing = await client.get("/api/v1/omnichannel/channel-orders", headers=headers)
    providers = sorted(r["provider"] for r in listing.json()["items"])
    assert providers == ["deliverect", "delivery_hero"]
