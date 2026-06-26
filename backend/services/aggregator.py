"""Aggregator ingest — Deliverect-class delivery middleware (F-060).

Brings delivery-aggregator orders (Jahez / HungerStation) into the POS. Per the SRS
the aggregators are **never** reached directly — an order arrives only through a
**Deliverect / Delivery-Hero-POS-partner middleware** webhook, which this module
ingests. A single ingested order does two things so aggregator revenue and inventory
reconcile with in-store sales:

1. it **materializes a tableless order ticket and fires it to the KDS**, so the
   kitchen prepares it exactly like a counter/floor order (F-057/F-058), and
2. it **books a real ZATCA sale through the shared sale core** (``services.sale_core``,
   slice 06) that decrements the **same shared stock pool** — identical compliance to
   an in-store POS sale.

Routing + tenancy mirror the Salla connector (``services.omnichannel``): the webhook
is unauthenticated (the middleware is the caller), so the order is routed to the
owning client by ``Clients.aggregator_location_id`` matching the payload's location,
and — when the client configured an ``aggregator_webhook_secret`` — the raw body's
HMAC-SHA256 signature is verified. Ingest is **idempotent** on
``(provider, external_order_id, client_id)`` via the existing ``channel_orders``
table, so webhook re-delivery never double-books a ticket or a sale.

The payload-parsing helpers are pure and unit-testable; ``ingest_aggregator_order``
orchestrates the DB work by composing the existing ``RestaurantService`` slices.
"""
import hashlib
import hmac
import json
import logging
from typing import Any, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.channel_orders import Channel_orders
from models.clients import Clients
from models.products import Products

logger = logging.getLogger(__name__)

# The Deliverect-class middleware connectors in scope (F-060). The actual aggregator
# (jahez / hungerstation) rides *inside* one of these as the order's ``channel``.
PROVIDERS: Tuple[str, ...] = ("deliverect", "delivery_hero")


# ---------- Webhook signature (F-060 security; same scheme as Salla) ----------
def verify_aggregator_signature(
    secret: Optional[str], raw_body: bytes, signature: Optional[str]
) -> bool:
    """Return whether ``signature`` is a valid HMAC-SHA256 of ``raw_body``.

    The middleware sends the hex HMAC-SHA256 of the raw request body keyed by the
    per-location webhook secret. When no secret is configured we skip verification
    (sandbox / graceful degradation, OPS-08) and return True; when a secret is set a
    missing/mismatched signature fails.
    """
    if not secret:
        return True
    if not signature:
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip().lower())


# ---------- Payload parsing (pure) ----------
def _as_float(value: Any) -> Optional[float]:
    """Coerce a middleware amount (number, or ``{"amount": ..}``) to float."""
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get("amount")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# Order-type normalization. A Deliverect ``orderType`` may arrive as a string
# (``"delivery"`` / ``"pickup"`` / ``"eatin"``) or its integer code (1 pickup,
# 2 delivery, 3 eat-in). Aggregator orders are always **tableless**, so an eat-in
# code collapses to ``takeaway`` (counter handover) — never a dine-in floor table.
_PICKUP_TOKENS = {"pickup", "takeaway", "collection", "1", "3", "eatin", "eat_in", "dinein", "dine_in"}


def _normalize_order_type(value: Any) -> str:
    token = str(value).strip().lower() if value is not None else ""
    if token in {"delivery", "2"}:
        return "delivery"
    if token in _PICKUP_TOKENS:
        return "takeaway"
    # Default an aggregator order to delivery (the dominant aggregator flow).
    return "delivery"


def extract_location(payload: dict) -> str:
    """Pull the middleware location id (the webhook's routing key) from a payload.

    Tolerant of the order living at the top level or under ``data``, and of the
    several spellings the middleware versions use.
    """
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    data = data or {}
    location = (
        payload.get("location")
        or payload.get("locationId")
        or data.get("location")
        or data.get("locationId")
        or data.get("location_id")
    )
    return str(location).strip() if location is not None else ""


def extract_aggregator_order(payload: dict) -> dict:
    """Normalize a Deliverect-class webhook payload into the fields the ingest needs.

    Returns ``external_order_id`` / ``external_reference`` / ``channel`` (the
    underlying aggregator) / ``order_type`` / customer / totals / ``items`` (the raw
    line list). Tolerant of the order living at the top level or under ``data``.
    """
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    data = data or {}

    external_order_id = (
        data.get("channelOrderId")
        or data.get("channel_order_id")
        or data.get("id")
        or data.get("order_id")
        or payload.get("id")
    )
    reference = (
        data.get("channelOrderDisplayId")
        or data.get("orderId")
        or data.get("reference")
        or data.get("order_number")
    )

    customer = data.get("customer") or {}
    name_parts = [customer.get("first_name"), customer.get("last_name")]
    customer_name = (
        customer.get("name")
        or " ".join(p for p in name_parts if p).strip()
        or None
    )
    customer_phone = (
        customer.get("phoneNumber")
        or customer.get("phone")
        or customer.get("mobile")
        or None
    )

    payment = data.get("payment") if isinstance(data.get("payment"), dict) else {}
    total_amount = _as_float(data.get("total")) or _as_float(payment.get("amount"))
    currency = data.get("currency") or payment.get("currency") or "SAR"

    return {
        "external_order_id": str(external_order_id) if external_order_id is not None else "",
        "external_reference": str(reference) if reference is not None else None,
        "channel": str(data.get("channel")).strip().lower() if data.get("channel") else None,
        "order_type": _normalize_order_type(data.get("orderType") or data.get("order_type")),
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "total_amount": total_amount,
        "currency": currency,
        "items": data.get("items") or [],
    }


async def _resolve_product(db: AsyncSession, client: Clients, item: dict):
    """Match one middleware line to the client's catalog (SEC-02 scoped).

    Matches by ``plu``/``sku``/``barcode`` against ``Products.barcode`` first, else by
    an exact (case-insensitive) name match. Returns the ``Products`` row or ``None``.
    """
    plu = (item.get("plu") or item.get("sku") or item.get("barcode") or "").strip()
    name = (item.get("name") or "").strip()
    product = None
    if plu:
        product = (
            await db.execute(
                select(Products).where(
                    Products.client_id == client.id,
                    Products.barcode == plu,
                )
            )
        ).scalar_one_or_none()
    if product is None and name:
        product = (
            await db.execute(
                select(Products).where(
                    Products.client_id == client.id,
                    Products.name.ilike(name),
                )
            )
        ).scalar_one_or_none()
    return product


# ---------- Ingest orchestration ----------
async def ingest_aggregator_order(
    db: AsyncSession,
    client: Clients,
    payload: dict,
    provider: str,
    vat_rate: float,
) -> dict:
    """Materialize an aggregator order as a fired KDS ticket + a ZATCA sale.

    Idempotent on ``(provider, external_order_id, client_id)``. Returns a status dict
    describing the outcome (``imported`` / ``duplicate`` / ``ignored``). On a fresh
    order: opens a tableless ticket (F-058), rings up the matched lines, fires the
    courses to the KDS (F-057), and settles the ticket into a real ZATCA invoice
    through the shared sale core (F-059/slice 06) — decrementing the same shared
    stock the in-store POS draws from. Online orders are pre-paid in the aggregator
    app, so the sale is booked as an out-of-band ``online`` tender and may oversell
    (``allow_negative_stock``).
    """
    # Local import avoids a circular import (restaurant service imports nothing here,
    # but keeping the dependency lazy mirrors the omnichannel connector).
    from services.restaurant import RestaurantService

    order = extract_aggregator_order(payload)
    external_id = order["external_order_id"]
    if not external_id:
        return {"status": "ignored", "reason": "missing_order_id"}

    # The owning client/user — captured up front so we never lazy-load the ORM row
    # after a rollback expires it (that would fault outside the async greenlet).
    client_id = client.id
    owner_user_id = client.user_id

    def _duplicate(row: Channel_orders) -> dict:
        return {
            "status": "duplicate",
            "channel_order_id": row.id,
            "transaction_id": row.transaction_id,
        }

    async def _find_existing() -> Optional[Channel_orders]:
        return (
            await db.execute(
                select(Channel_orders).where(
                    Channel_orders.client_id == client_id,
                    Channel_orders.provider == provider,
                    Channel_orders.external_order_id == external_id,
                )
            )
        ).scalar_one_or_none()

    # Idempotency — re-delivery of the same webhook must never double-book. Fast
    # SELECT pre-check first; the unique (client_id, provider, external_order_id)
    # constraint is the real arbiter on the claim insert below.
    existing = await _find_existing()
    if existing is not None:
        return _duplicate(existing)

    # DAT-07 idempotency-first: CLAIM the order (status="received") and commit BEFORE
    # any fiscal work. Minting the ZATCA invoice happens AFTER this row is durable, so
    # a crash between the signed invoice and recording the sale leaves the claim
    # behind — re-delivery sees it and refuses to mint a second invoice. On a
    # concurrent re-delivery that raced past the SELECT, the second insert conflicts
    # on the unique constraint and is treated as the duplicate.
    channel_order = Channel_orders(
        user_id=owner_user_id,
        client_id=client_id,
        provider=provider,
        external_order_id=external_id,
        external_reference=order["external_reference"],
        transaction_id=None,
        status="received",
        customer_name=order["customer_name"],
        customer_phone=order["customer_phone"],
        total_amount=order["total_amount"],
        currency=order["currency"],
        raw_payload=json.dumps(payload, ensure_ascii=False)[:20000],
    )
    db.add(channel_order)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await _find_existing()
        if existing is not None:
            return _duplicate(existing)
        raise
    channel_order_id = channel_order.id
    # The claim commit expired the client row; refresh it so the downstream ticket +
    # fiscal settle can read client.* without faulting on a lazy-load.
    await db.refresh(client)

    service = RestaurantService(db)
    label = f"{provider}:{order['channel'] or 'aggregator'} #{order['external_reference'] or external_id}"

    # 1) Open a tableless ticket driven by the order type (F-058).
    ticket = await service.create_ticket(
        {
            "order_type": order["order_type"],
            "customer_name": order["customer_name"],
            "notes": label,
        },
        client.user_id,
        client.id,
    )

    # 2) Ring up the lines. Matched lines carry a product_id (so stock decrements);
    #    an unmatched line still rings up (ad-hoc, no deduction) so the invoice total
    #    reflects what the customer paid.
    matched = 0
    for item in order["items"]:
        if not isinstance(item, dict):
            continue
        qty = _as_float(item.get("quantity")) or 0.0
        if qty <= 0:
            continue
        product = await _resolve_product(db, client, item)
        line: dict = {
            "qty": qty,
            "unit_price": _as_float(item.get("price")) or 0.0,
            "name": (item.get("name") or "").strip() or None,
        }
        if product is not None:
            matched += 1
            line["product_id"] = product.id
            line.setdefault("name", product.name)
        await service.add_item(ticket.id, line, client.user_id, client.id)

    # 3) Fire every present course to the KDS so the kitchen starts the order (F-057).
    items = await service.list_items(ticket.id, client.user_id)
    for course in sorted({(i.course or "mains") for i in items}):
        await service.fire_course(ticket.id, course, client.user_id)

    # 4) Settle into a real ZATCA invoice via the shared sale core (F-059/slice 06).
    #    Pre-paid in the aggregator app -> an out-of-band ``online`` tender; oversell
    #    allowed since the order is already accepted.
    check = await service.compute_check(ticket.id, client.user_id, vat_rate, 0.0)
    amount_due = check["amount_due"] if check else 0.0
    settled = await service.settle_ticket(
        ticket.id,
        client.user_id,
        client,
        vat_rate,
        tender_specs=[
            {"tender_type": "online", "amount": amount_due, "token": None, "simulate": None}
        ],
        payment_method="online",
        customer_name=order["customer_name"],
        allow_negative_stock=True,
    )
    transaction_id = settled["result"].transaction.id if settled else None

    # 5) Promote the claim to ``imported`` and link it to the materialized sale. The
    #    claim row was committed before the settle (DAT-07), so re-fetch it by id —
    #    execute_sale's intervening commit expired the original instance.
    claimed = (
        await db.execute(select(Channel_orders).where(Channel_orders.id == channel_order_id))
    ).scalar_one()
    claimed.transaction_id = transaction_id
    claimed.status = "imported" if transaction_id is not None else "received"
    await db.commit()

    logger.info(
        "Ingested %s order %s for client %s -> ticket %s, txn %s (%s line(s) matched)",
        provider, external_id, client_id, ticket.id, transaction_id, matched,
    )
    return {
        "status": "imported",
        "channel_order_id": channel_order_id,
        "ticket_id": ticket.id,
        "transaction_id": transaction_id,
        "matched_lines": matched,
    }
