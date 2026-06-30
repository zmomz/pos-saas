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
from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.channel_orders import Channel_orders
from models.clients import Clients
from models.products import Products
from models.restaurant import OrderTickets
from models.system_settings import System_settings

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
    per-location webhook secret.

    Fail closed (SEC-09): an unset/empty ``secret`` or a missing ``signature``
    returns ``False`` so the caller rejects. The webhook is unauthenticated and routed
    only by a guessable ``aggregator_location_id``; trusting an unsigned body whenever
    no secret was configured let anyone reaching the URL book sales against a connected
    location. A location with no secret therefore accepts no webhooks at all.
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

    async def _resume_existing(row: Channel_orders) -> Optional[dict]:
        """Decide what a re-delivery that found an existing claim should do (REV-02).

        Returns a terminal status dict to return immediately, or ``None`` to signal
        "resume settlement on this claim". A claim already carrying a transaction is
        fully settled (true duplicate). A claim still at ``received`` with no
        transaction is recoverable: if its ticket was already ``settled`` an invoice
        exists (the DAT-07 crash-AFTER-settle case) so we must NOT mint a second and
        report ``duplicate``; otherwise the settle never produced an invoice and we
        resume it. A claim with no ticket yet (or a no-lines DAT-08 order) simply
        re-runs from scratch.
        """
        if row.transaction_id is not None:
            return _duplicate(row)
        if row.ticket_id is not None:
            ticket = (
                await db.execute(select(OrderTickets).where(OrderTickets.id == row.ticket_id))
            ).scalar_one_or_none()
            if ticket is not None and (ticket.status or "open") in ("settled", "void"):
                # Invoice already minted on the first attempt — never double-invoice.
                return _duplicate(row)
        return None

    async def _acquire_settle_lock(co_id: int) -> bool:
        """Atomically transition the claim ``received -> settling`` (REV-05).

        Returns ``True`` iff THIS caller won the settle lock. The aggregator
        middleware re-delivers (sometimes concurrently); REV-02's resume path used to
        re-run settlement for ANY claim still at ``received`` with no transaction, with
        no mutual exclusion, so two concurrent re-deliveries both opened a ticket and
        minted an invoice (#179). This conditional UPDATE is the sole settle arbiter:
        exactly one caller flips ``received -> settling`` (the unique-insert winner of a
        fresh claim, or one re-delivery of a stuck one); every other caller sees a
        non-``received`` status, gets ``rowcount == 0``, and backs off as a duplicate.
        ``settling_at`` stamps when the lock was taken so the bounded sweep can recover
        a settler that crashed mid-flight without any concurrent caller resuming on
        sight.
        """
        result = await db.execute(
            update(Channel_orders)
            .where(
                Channel_orders.id == co_id,
                Channel_orders.status == "received",
                Channel_orders.transaction_id.is_(None),
            )
            .values(status="settling", settling_at=datetime.now(timezone.utc))
        )
        await db.commit()
        return (result.rowcount or 0) == 1

    async def _release_settle_lock(co_id: int) -> None:
        """Hand the settle lock back to ``received`` after an IN-PROCESS settle failure.

        A settle that raises in-process is observable, so we re-open the claim
        immediately for the next re-delivery to resume. A HARD crash never reaches this
        path — the claim stays ``settling`` and only the bounded sweep recovers it once
        it is demonstrably stuck.
        """
        await db.rollback()  # discard the failed settle's pending (uncommitted) work
        await db.execute(
            update(Channel_orders)
            .where(Channel_orders.id == co_id, Channel_orders.status == "settling")
            .values(status="received", settling_at=None)
        )
        await db.commit()

    # Idempotency — re-delivery of the same webhook must never double-book. Fast
    # SELECT pre-check first; the unique (client_id, provider, external_order_id)
    # constraint is the real arbiter on the claim insert below, and the
    # ``received -> settling`` CAS (acquired before any fiscal work) is the sole
    # settle arbiter against concurrent re-deliveries.
    existing = await _find_existing()
    resume_ticket: Optional[OrderTickets] = None
    if existing is not None:
        terminal = await _resume_existing(existing)
        if terminal is not None:
            return terminal
        # REV-02/REV-05: a stuck claim (committed "received" but the settle never
        # produced an invoice — the process died or execute_sale raised after the
        # DAT-07 claim commit). It is *recoverable*, but a concurrent re-delivery must
        # not resume it on sight; the ``received -> settling`` CAS below serializes
        # them so exactly one re-delivery re-attempts settlement (re-using the durable
        # ticket so the kitchen order isn't duplicated).
        channel_order_id = existing.id
        logger.info(
            "Aggregator %s order %s for client %s: found stuck claim %s "
            "(received, no transaction; ticket %s) -> contending for the settle lock",
            provider, external_id, client_id, channel_order_id, existing.ticket_id,
        )
    else:
        # DAT-07 idempotency-first: CLAIM the order (status="received") and commit
        # BEFORE any fiscal work. Minting the ZATCA invoice happens AFTER this row is
        # durable, so a crash between the signed invoice and recording the sale leaves
        # the claim behind — re-delivery sees it and (REV-02) recovers it. On a
        # concurrent re-delivery that raced past the SELECT, the second insert
        # conflicts on the unique constraint and is treated as the duplicate (the
        # insert-winner is the single settler — preserving DAT-07's concurrency
        # guarantee that exactly one delivery ever settles).
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

    # DAT-08 empty-order guard: a payload whose lines are all missing or non-billable
    # (qty <= 0, or not a line object) has nothing to ring up. Opening a ticket and
    # firing the KDS for it would leave an orphan ticket + KDS card and drive a
    # zero-line settle that 500s on webhook re-delivery. The order is already claimed
    # above (idempotency marker durable), so simply stop here and report ``no_lines``
    # — mirroring Salla's graceful behaviour (services/omnichannel.py). The claim row
    # stays at ``received`` with no transaction; a re-delivery dedupes against it.
    billable = [
        item
        for item in order["items"]
        if isinstance(item, dict) and (_as_float(item.get("quantity")) or 0.0) > 0
    ]
    if not billable:
        logger.info(
            "Aggregator %s order %s for client %s has no billable lines -> no_lines (claim %s)",
            provider, external_id, client_id, channel_order_id,
        )
        return {
            "status": "no_lines",
            "channel_order_id": channel_order_id,
            "ticket_id": None,
            "transaction_id": None,
            "matched_lines": 0,
        }

    # REV-05: win the settle lock BEFORE any fiscal work. Exactly one caller flips
    # ``received -> settling``; a concurrent re-delivery loses the CAS and backs off as
    # a duplicate, so one order never mints two invoices / two KDS tickets (#179).
    if not await _acquire_settle_lock(channel_order_id):
        current = await _find_existing()
        logger.info(
            "Aggregator %s order %s for client %s: lost the settle lock on claim %s "
            "-> another delivery is settling; reporting duplicate",
            provider, external_id, client_id, channel_order_id,
        )
        if current is not None:
            return _duplicate(current)
        return {"status": "duplicate", "channel_order_id": channel_order_id, "transaction_id": None}

    # The CAS commit expired the client + claim rows; reload what the settle reads. The
    # claim may already carry a ticket materialized before a crash (REV-02) — re-use it.
    await db.refresh(client)
    locked = (
        await db.execute(select(Channel_orders).where(Channel_orders.id == channel_order_id))
    ).scalar_one()
    if locked.ticket_id is not None:
        resume_ticket = (
            await db.execute(select(OrderTickets).where(OrderTickets.id == locked.ticket_id))
        ).scalar_one_or_none()

    # We hold the settle lock (status="settling"). Everything below is the single,
    # serialized settle for this claim; an in-process failure releases the lock back to
    # ``received`` so a re-delivery resumes, while a hard crash leaves it ``settling``
    # for the bounded sweep.
    try:
        service = RestaurantService(db)
        label = f"{provider}:{order['channel'] or 'aggregator'} #{order['external_reference'] or external_id}"

        if resume_ticket is not None:
            # REV-02 resume: the ticket, its lines, and fired courses were all committed
            # before the failed settle — re-use them as-is so the kitchen order is never
            # duplicated. Jump straight to the (previously failed) settle.
            ticket = resume_ticket
            items = await service.list_items(ticket.id, client.user_id)
            matched = sum(1 for i in items if getattr(i, "product_id", None) is not None)
        else:
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
            # REV-02: link the ticket to the claim and commit BEFORE the fiscal settle so
            # a crash mid-settle is recoverable — a re-delivery re-uses this exact ticket
            # (re-settling it, or detecting it already settled). The settle lock is held
            # across this commit (the conditional UPDATE only touches status), so the
            # claim stays ``settling`` and no concurrent caller can also create a ticket.
            await db.execute(
                update(Channel_orders)
                .where(Channel_orders.id == channel_order_id)
                .values(ticket_id=ticket.id)
            )
            await db.commit()

            # 2) Ring up the lines. Matched lines carry a product_id (so stock decrements);
            #    an unmatched line still rings up (ad-hoc, no deduction) so the invoice
            #    total reflects what the customer paid.
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

            # 3) Fire every present course to the KDS so the kitchen starts the order
            #    (F-057).
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

        # 5) Promote the claim to ``imported`` and link it to the materialized sale,
        #    releasing the settle lock (``settling_at`` cleared). The claim row was
        #    committed before the settle (DAT-07), so re-fetch it by id — execute_sale's
        #    intervening commit expired the original instance.
        claimed = (
            await db.execute(select(Channel_orders).where(Channel_orders.id == channel_order_id))
        ).scalar_one()
        claimed.transaction_id = transaction_id
        claimed.status = "imported" if transaction_id is not None else "received"
        claimed.settling_at = None
        await db.commit()
    except Exception:
        # In-process settle failure: release the lock so a re-delivery resumes.
        await _release_settle_lock(channel_order_id)
        raise

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


# ---------- Bounded crash-recovery sweep (REV-05) ----------
# How long a claim may hold the ``settling`` lock before the sweep treats its settler
# as crashed and re-opens it. Shared by the recovery sweep and the operator-facing
# status read so the UI's "stuck" definition matches exactly what the sweep recovers.
STUCK_CLAIM_THRESHOLD_SECONDS = 600

# system_settings KV key holding the last unattended sweep run (JSON: ran_at, reopened).
SWEEP_STATUS_KEY = "omnichannel_sweep_last_run"


async def recover_stuck_aggregator_claims(
    db: AsyncSession,
    threshold_seconds: int = STUCK_CLAIM_THRESHOLD_SECONDS,
    now: Optional[datetime] = None,
) -> int:
    """Re-open aggregator claims whose settler crashed mid-flight (#179).

    The settle lock (``received -> settling`` CAS) makes the resume path mutually
    exclusive, but a settler that dies HARD between acquiring the lock and finishing
    leaves the claim stranded at ``settling`` forever — a concurrent re-delivery is
    deliberately *not* allowed to resume it on sight (that was the double-settle bug).
    This bounded sweep is the only recovery: it flips any claim that has been
    ``settling`` longer than ``threshold_seconds`` back to ``received`` (clearing the
    lock stamp) so the next webhook re-delivery resumes it, while leaving a freshly
    locked claim — a settle genuinely in flight — alone. Returns the count re-opened.

    The age check is done in Python so it is dialect-agnostic (SQLite returns naive
    datetimes; Postgres aware) — naive stamps are read as UTC.
    """
    now = now or datetime.now(timezone.utc)
    rows = (
        await db.execute(
            select(Channel_orders).where(Channel_orders.status == "settling")
        )
    ).scalars().all()

    reopened = 0
    for row in rows:
        stamped = row.settling_at
        if stamped is None:
            # No stamp on a ``settling`` row should not happen, but treat it as stuck.
            age = float(threshold_seconds) + 1.0
        else:
            if stamped.tzinfo is None:
                stamped = stamped.replace(tzinfo=timezone.utc)
            age = (now - stamped).total_seconds()
        if age >= threshold_seconds:
            row.status = "received"
            row.settling_at = None
            reopened += 1
            logger.info(
                "REV-05 sweep: re-opened stuck aggregator claim %s (settling for %.0fs)",
                row.id, age,
            )

    if reopened:
        await db.commit()
    return reopened


# ---------- Operator-facing sweep status (#237) ----------
async def record_omnichannel_sweep_run(
    db: AsyncSession,
    reopened: int,
    now: Optional[datetime] = None,
) -> None:
    """Persist the last unattended sweep run so the UI can show when it last ran.

    Written once per scheduler tick (after :func:`recover_stuck_aggregator_claims`)
    into the platform-wide ``system_settings`` KV — no migration, one row per key.
    Stores ``ran_at`` (ISO) and ``reopened`` (how many stuck claims were recovered).
    """
    now = now or datetime.now(timezone.utc)
    payload = json.dumps({"ran_at": now.isoformat(), "reopened": int(reopened)})
    row = (
        await db.execute(
            select(System_settings).where(System_settings.key == SWEEP_STATUS_KEY)
        )
    ).scalar_one_or_none()
    if row is None:
        db.add(System_settings(key=SWEEP_STATUS_KEY, value=payload))
    else:
        row.value = payload
    await db.commit()


async def omnichannel_sweep_status(
    db: AsyncSession,
    client_id: int,
    *,
    threshold_seconds: int = STUCK_CLAIM_THRESHOLD_SECONDS,
    now: Optional[datetime] = None,
) -> dict:
    """Report stuck-claim health for one client plus the last unattended sweep run.

    A claim is *stuck* when it has held the ``settling`` lock past ``threshold_seconds``
    — the exact condition :func:`recover_stuck_aggregator_claims` recovers, so a non-zero
    count means a settler crashed and the sweep has not caught up yet (un-healthy). A
    freshly locked claim (settle genuinely in flight) is healthy. Owner-scoped to
    ``client_id`` (SEC-02). The age check runs in Python so it is dialect-agnostic
    (SQLite naive stamps are read as UTC), mirroring the recovery sweep.
    """
    now = now or datetime.now(timezone.utc)
    stamps = (
        await db.execute(
            select(Channel_orders.settling_at).where(
                Channel_orders.client_id == client_id,
                Channel_orders.status == "settling",
            )
        )
    ).scalars().all()

    stuck = 0
    oldest: Optional[float] = None
    for stamped in stamps:
        if stamped is None:
            # A ``settling`` row with no stamp should not happen; treat it as stuck.
            age = float(threshold_seconds) + 1.0
        else:
            if stamped.tzinfo is None:
                stamped = stamped.replace(tzinfo=timezone.utc)
            age = (now - stamped).total_seconds()
        if age >= threshold_seconds:
            stuck += 1
            if oldest is None or age > oldest:
                oldest = age

    last_run_at: Optional[str] = None
    last_reopened: Optional[int] = None
    row = (
        await db.execute(
            select(System_settings).where(System_settings.key == SWEEP_STATUS_KEY)
        )
    ).scalar_one_or_none()
    if row and row.value:
        try:
            data = json.loads(row.value)
            last_run_at = data.get("ran_at")
            last_reopened = data.get("reopened")
        except (ValueError, TypeError):  # pragma: no cover - corrupt KV row
            pass

    return {
        "last_run_at": last_run_at,
        "last_reopened": last_reopened,
        "stuck_count": stuck,
        "oldest_stuck_age_seconds": oldest,
        "threshold_seconds": threshold_seconds,
        "healthy": stuck == 0,
    }
