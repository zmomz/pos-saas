"""Omnichannel ingest — Salla online-store orders (OMN-01/03, F-046).

The first connector of the "sell online too" vision. A Salla webhook pushes an
``order.created`` event to ``POST /api/v1/omnichannel/salla/webhook``; this module
turns it into a real POS sale so the online order:

- appears in the back-office (it is a ``Transactions`` row, OMN-03),
- decrements the **same shared stock pool** the in-store POS deducts from (OMN-03 —
  we route it through the identical atomic sale path used by offline replay), and
- is ZATCA-signed + hash-chained like any sale.

Routing + tenancy: the webhook is unauthenticated (Salla is the caller), so the
order is routed to the owning client by ``Clients.salla_store_id`` matching the
``merchant`` field, and — when the client configured a ``salla_webhook_secret`` —
the request body's HMAC-SHA256 signature is verified. Idempotency is keyed on
``(provider, external_order_id, client_id)`` so re-delivery never double-books.

The payload-parsing helpers are pure and unit-testable; ``ingest_salla_order``
orchestrates the DB work.
"""
import hashlib
import hmac
import json
import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.channel_orders import Channel_orders
from models.clients import Clients
from models.products import Products
from models.transactions import Transactions

logger = logging.getLogger(__name__)

PROVIDER_SALLA = "salla"


# ---------- Webhook signature (OMN-01 security) ----------
def verify_salla_signature(secret: Optional[str], raw_body: bytes, signature: Optional[str]) -> bool:
    """Return whether ``signature`` is a valid HMAC-SHA256 of ``raw_body``.

    Salla's "Signature" security strategy sends ``X-Salla-Signature`` = the hex
    HMAC-SHA256 of the raw request body keyed by the webhook secret.

    Fail closed (SEC-09): an unset/empty ``secret`` or a missing ``signature``
    returns ``False`` so the caller rejects. The Salla webhook is unauthenticated and
    routed only by a guessable ``salla_store_id``; trusting an unsigned body whenever
    no secret was configured let anyone reaching the URL book sales against a
    connected store. A store with no secret therefore accepts no webhooks at all.
    """
    if not secret or not signature:
        return False
    candidate = signature.strip().lower()
    if not candidate.isascii():
        # ``compare_digest`` raises TypeError on a non-ASCII str (-> 500); a real
        # hex digest is always ASCII, so this is just a malformed signature.
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, candidate)


# ---------- Payload parsing (pure) ----------
def _as_float(value: Any) -> Optional[float]:
    """Coerce a Salla amount (number, or ``{"amount": .., "currency": ..}``) to float."""
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get("amount")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_unit_price(item: dict) -> float:
    """Best-effort net unit price for a Salla order line.

    Salla nests price under several shapes across API/webhook versions; prefer a
    tax-exclusive figure (VAT is recomputed on the sale), then fall back to the
    gross price, then total/quantity. Returns 0.0 when nothing is parseable.
    """
    amounts = item.get("amounts") or {}
    qty = _as_float(item.get("quantity")) or 0.0
    candidates = [
        amounts.get("price_without_tax"),
        (amounts.get("price") if isinstance(amounts, dict) else None),
        ((item.get("product") or {}).get("price") if isinstance(item.get("product"), dict) else None),
        item.get("price"),
    ]
    for cand in candidates:
        price = _as_float(cand)
        if price is not None:
            return price
    # Last resort: derive from the line total.
    total = _as_float(amounts.get("total")) or _as_float(item.get("total"))
    if total is not None and qty:
        return round(total / qty, 4)
    return 0.0


def extract_salla_order(payload: dict) -> dict:
    """Normalize a Salla webhook payload into the fields the ingest needs.

    Tolerant of the order living at the top level or under ``data``. Returns a dict
    with ``external_order_id`` / ``external_reference`` / ``merchant`` / customer /
    totals / ``items`` (the raw line list).
    """
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    data = data or {}

    external_order_id = data.get("id") or data.get("order_id") or payload.get("id")
    reference = data.get("reference_id") or data.get("reference") or data.get("order_number")

    customer = data.get("customer") or {}
    name_parts = [customer.get("first_name"), customer.get("last_name")]
    customer_name = (
        customer.get("name")
        or " ".join(p for p in name_parts if p).strip()
        or None
    )
    customer_phone = customer.get("mobile") or customer.get("phone") or None

    totals = data.get("total") or data.get("amounts", {}).get("total") or {}
    total_amount = _as_float(totals)
    currency = (totals.get("currency") if isinstance(totals, dict) else None) or "SAR"

    return {
        "merchant": payload.get("merchant") or data.get("merchant") or data.get("store_id"),
        "external_order_id": str(external_order_id) if external_order_id is not None else "",
        "external_reference": str(reference) if reference is not None else None,
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "total_amount": total_amount,
        "currency": currency,
        "items": data.get("items") or [],
    }


async def _match_line_items(db: AsyncSession, client: Clients, raw_items: list) -> tuple[list[dict], int]:
    """Map Salla order lines to the client's products → POS cart-item dicts.

    Matches by ``sku``/``barcode`` against ``Products.barcode`` first, else by an
    exact (case-insensitive) name match — both scoped to the client (SEC-02). Only
    matched lines become sale lines (they carry a ``product_id`` so stock decrements);
    unmatched lines are skipped. Returns ``(txn_items, matched_count)``.
    """
    txn_items: list[dict] = []
    matched = 0
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        # Keep the line quantity as a float (INV-01): a weighted / fractional line
        # (e.g. 1.5 kg) must not be int()-truncated to 1. Matches the aggregator
        # connector, which also carries float qty. A zero (or unparseable) line is
        # still skipped.
        qty = _as_float(item.get("quantity")) or 0.0
        if qty <= 0:
            continue
        sku = (item.get("sku") or item.get("barcode") or "").strip()
        name = (item.get("name") or "").strip()

        product = None
        if sku:
            product = (
                await db.execute(
                    select(Products).where(
                        Products.client_id == client.id,
                        Products.barcode == sku,
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
        if product is None:
            logger.info(
                "Salla order line unmatched (sku=%r name=%r) for client %s — skipped",
                sku, name, client.id,
            )
            continue

        matched += 1
        txn_items.append(
            {
                "product_id": product.id,
                "name": product.name,
                "price": _extract_unit_price(item),
                "quantity": qty,
                "discount": 0,
            }
        )
    return txn_items, matched


async def ingest_salla_order(db: AsyncSession, client: Clients, payload: dict) -> dict:
    """Materialize a Salla order as a POS sale + record the channel order.

    Idempotent on ``(provider, external_order_id, client_id)``. Returns a status
    dict describing the outcome (``imported`` / ``duplicate`` / ``no_lines``).
    """
    order = extract_salla_order(payload)
    external_id = order["external_order_id"]
    if not external_id:
        return {"status": "ignored", "reason": "missing_order_id"}

    # Idempotency — never double-book a re-delivered webhook.
    existing = (
        await db.execute(
            select(Channel_orders).where(
                Channel_orders.client_id == client.id,
                Channel_orders.provider == PROVIDER_SALLA,
                Channel_orders.external_order_id == external_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return {
            "status": "duplicate",
            "channel_order_id": existing.id,
            "transaction_id": existing.transaction_id,
        }

    txn_items, matched = await _match_line_items(db, client, order["items"])

    transaction_id: Optional[int] = None
    if txn_items:
        # Route through the SAME atomic sale path as offline replay (POS-05): invoice
        # counter, shared-stock deduction, shift accumulation, tender ledger, and
        # ECDSA signing — all committed together. Online orders are already settled
        # in the store, so we accept them even if stock would go negative (oversell),
        # then decrement the shared pool. Imported lazily to avoid an import cycle.
        from routers.pos import process_offline_sale

        offline_id = f"salla:{client.id}:{external_id}"
        txn = {
            "items": txn_items,
            "payment_method": "online",
            "customer_name": order["customer_name"],
            "customer_phone": order["customer_phone"],
            "discount_amount": 0,
            "allow_negative_stock": True,
            "offline_id": offline_id,
        }
        result = await process_offline_sale(db, client.user_id, client.id, txn)
        transaction_id = result.get("transaction_id")
        if transaction_id is None:
            # The dedupe guard skipped it (the same offline_id already materialized a
            # sale in a prior partial run) — recover the existing transaction id so
            # the channel record still links correctly.
            prior = (
                await db.execute(
                    select(Transactions.id).where(
                        Transactions.user_id == client.user_id,
                        Transactions.offline_id == offline_id,
                    )
                )
            ).scalar_one_or_none()
            transaction_id = prior

    channel_order = Channel_orders(
        user_id=client.user_id,
        client_id=client.id,
        provider=PROVIDER_SALLA,
        external_order_id=external_id,
        external_reference=order["external_reference"],
        transaction_id=transaction_id,
        status="imported" if transaction_id is not None else "received",
        customer_name=order["customer_name"],
        customer_phone=order["customer_phone"],
        total_amount=order["total_amount"],
        currency=order["currency"],
        raw_payload=json.dumps(payload, ensure_ascii=False)[:20000],
    )
    db.add(channel_order)
    await db.commit()
    await db.refresh(channel_order)

    return {
        "status": "imported" if transaction_id is not None else "no_lines",
        "channel_order_id": channel_order.id,
        "transaction_id": transaction_id,
        "matched_lines": matched,
    }
