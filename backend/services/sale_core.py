"""The one fiscal sale path — `06-sale-core-extraction`.

The POS atomic sale — tender capture → invoice counter → inventory deduction
(incl. BOM expansion) → shift accumulation → ECDSA sign / hash-chain / archive,
**all committed together** — used to live inline in
``routers/pos.py::create_transaction``. Both the restaurant settle-to-invoice
path (F-059) and the aggregator ingest (F-060) need to mint an *identical*
fiscal sale, so the compliance-critical sequence is extracted here once instead
of forked three ways.

:func:`execute_sale` takes a :class:`NormalizedCart` — line items, captured-tender
specs, customer/VAT, branch, tip, **service charge** (F-061) and optional
**BOM expansion** (F-062) — and performs the full atomic sequence in the caller's
session, committing once. It returns the persisted transaction plus the fiscal
document linkage in a :class:`SaleResult`.

The extraction is **behavior-preserving** for the existing POS path: the helper
functions below are the very ones the POS handler used (moved here so the offline
and refund paths import them unchanged), and the sequence in :func:`execute_sale`
mirrors the old inline order exactly. A failure anywhere in the sequence rolls the
whole sale back — no orphan invoice, no partial stock deduction (POS atomicity).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.clients import Clients
from models.payment_tenders import PaymentTenders
from models.products import Products
from models.terminals import Terminals
from models.transactions import Transactions
from services import loyalty as loyalty_service
from services import zatca_sale
from services.gift_cards import GiftCardError, GiftCardsService
from services.payment_gateway import (
    GatewayNotConfigured,
    PaymentDeclined,
    get_gateway,
    get_terminal_gateway,
    normalize_tender_type,
    requires_capture,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Atomic-sale helpers (moved verbatim from routers/pos.py so the offline-sync
# and refund paths keep importing them unchanged).
# ---------------------------------------------------------------------------
async def deduct_inventory(
    db: AsyncSession,
    client_id: int,
    items: List[Any],
    allow_negative_stock: bool,
) -> None:
    """Decrement product stock for the sold items within the caller's transaction.

    Does NOT commit — the caller commits the sale and the deductions together so
    the whole sale is atomic. Raises HTTPException(400) on insufficient stock
    (unless ``allow_negative_stock``), which rolls the sale back.

    Lines whose ``product_id`` does not map to one of the client's products are
    skipped (e.g. ad-hoc/custom line items), preserving prior behavior.
    """
    # Aggregate requested quantities per product (an item may appear twice).
    # Float keys the value so weighted lines (fractional qty, POS-11/F-011) deduct
    # the real amount sold.
    requested: dict[int, float] = {}
    for item in items:
        requested[item.product_id] = requested.get(item.product_id, 0) + item.quantity

    for product_id, qty in requested.items():
        result = await db.execute(
            select(Products).where(
                Products.id == product_id,
                Products.client_id == client_id,
            )
        )
        product = result.scalar_one_or_none()
        if not product:
            # Unknown/ad-hoc line — nothing to deduct.
            continue

        available = product.quantity or 0
        if not allow_negative_stock and available < qty:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Insufficient stock for '{product.name}': "
                    f"requested {qty}, available {available}"
                ),
            )

        new_qty = available - qty
        if not allow_negative_stock:
            new_qty = max(0, new_qty)

        await db.execute(
            update(Products)
            .where(Products.id == product_id)
            .values(quantity=new_qty)
        )


async def deduct_bom_components(
    db: AsyncSession,
    user_id: str,
    client_id: int,
    sold_lines: List[tuple],
    allow_negative_stock: bool,
) -> None:
    """Expand BOM-backed sold lines and deduct their components (F-062, no commit).

    ``sold_lines`` is a list of ``(product_id, qty_sold)``. Each BOM-backed parent
    expands into ``qty_per × qty_sold`` of every component (shared components fold
    together); a finished good with no BOM contributes nothing. The aggregated
    component deductions are applied within the caller's transaction so they commit
    atomically with the sale — a shortfall raises HTTPException(400) **before**
    commit (unless overselling is allowed), rolling the whole sale back so a failed
    depletion never leaves a partial component deduction.

    This is where the sale core owns BOM expansion: the settle path (F-059) and any
    other caller turns it on via ``NormalizedCart.expand_bom`` and the recipe is
    depleted inside the same atomic stock transaction as the finished sale.
    """
    from models.restaurant import BillOfMaterials

    deductions: Dict[int, float] = {}
    for product_id, qty in sold_lines:
        if product_id is None:
            continue
        rows = (
            await db.execute(
                select(BillOfMaterials).where(
                    BillOfMaterials.parent_product_id == int(product_id),
                    BillOfMaterials.user_id == user_id,
                )
            )
        ).scalars().all()
        for entry in rows:
            add = float(entry.qty_per or 0) * float(qty or 0)
            cid = entry.component_product_id
            deductions[cid] = deductions.get(cid, 0.0) + add

    for component_id, qty in deductions.items():
        product = (
            await db.execute(
                select(Products).where(
                    Products.id == component_id,
                    Products.client_id == client_id,
                )
            )
        ).scalar_one_or_none()
        if not product:
            # Component product was deleted / not owned — nothing to deduct.
            continue
        available = float(product.quantity or 0)
        if not allow_negative_stock and available < qty:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Insufficient stock for component '{product.name}': "
                    f"requested {qty}, available {available}"
                ),
            )
        new_qty = available - qty
        if not allow_negative_stock:
            new_qty = max(0.0, new_qty)
        await db.execute(
            update(Products)
            .where(Products.id == component_id)
            .values(quantity=new_qty)
        )


async def apply_sale_to_open_shift(
    db: AsyncSession, user_id: str, amount: float
) -> Optional[int]:
    """Add ``amount`` (and one transaction) to the user's open shift, if any.

    Returns the shift id so the sale can be linked to it (``Transactions.shift_id``).
    Runs inside the caller's transaction so the shift totals and the sale commit
    together. Refunds pass a negative ``amount`` so reconciliation nets out. Returns
    None when no shift is open (sales are still allowed without a shift).
    """
    from models.shifts import Shifts

    result = await db.execute(
        select(Shifts).where(Shifts.user_id == user_id, Shifts.status == "open")
    )
    shift = result.scalar_one_or_none()
    if not shift:
        return None
    await db.execute(
        update(Shifts)
        .where(Shifts.id == shift.id)
        .values(
            total_sales=(shift.total_sales or 0) + amount,
            total_transactions=(shift.total_transactions or 0) + 1,
        )
    )
    return shift.id


async def capture_tenders(specs: List[dict]) -> List[dict]:
    """Capture each tender via the active gateway, returning persistable rows.

    For a card-like tender (card/mada/applepay/stcpay/tabby/tamara) the gateway is
    asked for a real approval; a decline (or an unconfigured real gateway) raises
    ``HTTPException(402)``. Because the caller is mid-transaction and has not
    committed, that raise rolls the whole sale back — a declined card never leaves
    a persisted sale (F-001). Cash/transfer/loyalty settle internally and are
    recorded without a gateway round-trip.

    Each spec is ``{tender_type|method, amount, token, simulate, _gateway?}``. A
    spec may carry a pre-resolved ``_gateway`` (an in-store SoftPOS terminal — set
    by :func:`attach_terminal_gateways`); otherwise the active online/sandbox
    gateway captures it.
    """
    default_gateway = get_gateway()
    captured: List[dict] = []
    for spec in specs:
        gateway = spec.get("_gateway") or default_gateway
        ttype = normalize_tender_type(spec.get("tender_type") or spec.get("method"))
        amount = round(float(spec.get("amount") or 0), 2)
        # Gift-card legs settle against the card balance (a DB side effect), not a
        # gateway — they are validated + decremented by ``redeem_gift_cards`` which
        # has the db session and owner scope. Skip them here to avoid a duplicate row.
        if ttype == "giftcard":
            continue
        row = {
            "tender_type": ttype,
            "amount": amount,
            "gateway": None,
            "status": "captured",
            "network": None,
            "approval_code": None,
            "rrn": None,
            "gateway_ref": None,
            "last4": None,
            "token": None,
            "decline_reason": None,
        }
        if requires_capture(ttype) and amount > 0:
            try:
                result = await gateway.charge(
                    amount,
                    ttype,
                    token=spec.get("token"),
                    simulate=spec.get("simulate"),
                )
            except GatewayNotConfigured as exc:
                logger.warning("Tender capture not configured for %s: %s", ttype, exc)
                raise HTTPException(status_code=402, detail=f"Payment not captured: {exc}")
            except PaymentDeclined as exc:
                logger.info("Tender %s declined by %s: %s", ttype, exc.gateway, exc.reason)
                raise HTTPException(status_code=402, detail=f"Payment declined: {exc.reason}")
            if not result.approved:
                raise HTTPException(
                    status_code=402,
                    detail=f"Payment declined for {ttype}: {result.decline_reason or 'declined'}",
                )
            row.update(
                gateway=result.gateway,
                network=result.network,
                approval_code=result.approval_code,
                rrn=result.rrn,
                gateway_ref=result.gateway_ref,
                last4=result.last4,
                token=result.token,
            )
        captured.append(row)
    return captured


async def redeem_gift_cards(
    db: AsyncSession, user_id: str, client_id: int, specs: List[dict]
) -> List[dict]:
    """Redeem every gift-card tender leg against its card balance (PRC-05, F-038).

    For each spec whose tender is a gift card, the bearer code is validated
    (exists in the caller's scope, active, unexpired, enough balance) and the
    card's balance is **atomically decremented** in the caller's transaction — so a
    later card decline (or any failure) rolls the decrement back with the sale, and
    concurrent sales cannot overdraw a card. An invalid/insufficient card raises
    ``HTTPException(400)`` *before* any card is charged (this runs ahead of the
    gateway capture), so the sale fails closed with nothing committed.

    Returns the persistable ``giftcard`` tender rows (linked to the sale by the
    caller). The row carries ``gateway="giftcard"``, a ``giftcard:<id>`` reference
    (for a future refund-to-card), and the code's last 4 — never the full code.
    """
    service = GiftCardsService(db)
    rows: List[dict] = []
    for spec in specs:
        ttype = normalize_tender_type(spec.get("tender_type") or spec.get("method"))
        if ttype != "giftcard":
            continue
        amount = round(float(spec.get("amount") or 0), 2)
        if amount <= 0:
            continue
        code = (spec.get("gift_card_code") or "").strip()
        if not code:
            raise HTTPException(
                status_code=400, detail="A gift card code is required for a gift-card tender"
            )
        try:
            card = await service.validate(code, amount, user_id=user_id)
        except GiftCardError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        if not await service.redeem(card.id, amount, user_id=user_id):
            # Lost the balance race between validate and redeem — treat as exhausted.
            raise HTTPException(
                status_code=400, detail="This gift card has insufficient balance"
            )
        rows.append(
            {
                "tender_type": "giftcard",
                "amount": amount,
                "gateway": "giftcard",
                "status": "captured",
                "network": None,
                "approval_code": None,
                "rrn": None,
                "gateway_ref": f"giftcard:{card.id}",
                "last4": (card.code or "")[-4:],
                "token": None,
                "decline_reason": None,
            }
        )
    return rows


async def attach_terminal_gateways(
    db: AsyncSession, user_id: str, specs: List[dict]
) -> None:
    """Resolve an in-store SoftPOS terminal for any spec that names one (HW-03/F-005).

    For each spec carrying a ``terminal_id``, verify the terminal belongs to the
    caller (SEC-02) and is active, then attach its provider's gateway as
    ``spec["_gateway"]`` so :func:`capture_tenders` pushes that leg to the paired
    terminal for a real approval. A card leg with no terminal still routes to the
    active online/sandbox gateway. An unknown/foreign/inactive terminal is a 400 so
    the sale fails closed rather than silently falling back to the online gateway.
    """
    for spec in specs:
        terminal_id = spec.get("terminal_id")
        if not terminal_id:
            continue
        terminal = (
            await db.execute(
                select(Terminals).where(
                    Terminals.id == terminal_id,
                    Terminals.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if terminal is None:
            raise HTTPException(status_code=400, detail=f"Terminal {terminal_id} not found")
        if (terminal.status or "active") != "active":
            raise HTTPException(status_code=400, detail=f"Terminal {terminal_id} is not active")
        spec["_gateway"] = get_terminal_gateway(terminal.provider)


async def snapshot_cost_prices(
    db: AsyncSession,
    client_id: int,
    lines: List[Any],
    line_dicts: List[dict],
) -> None:
    """Stamp each sold line's product ``cost_price`` onto its items_json dict (F-068).

    Historical margin must be **stable** — computed from the cost at sale time, not
    recomputed later from the product's current (moving-average) cost. So at sale
    time we snapshot the catalog cost onto the line. The profit/margin report reads
    this snapshot in preference to the live cost.

    Purely **additive and behavior-preserving**: it only fills a ``cost_price`` key
    that isn't already present and touches nothing else on the line, so the atomic
    sale (stock, totals, signing) is unchanged. Lines whose ``product_id`` doesn't
    map to one of the client's products (ad-hoc lines) are left without a cost.
    """
    pids = {int(p) for it in lines if (p := getattr(it, "product_id", None)) is not None}
    if not pids:
        return
    rows = (
        await db.execute(
            select(Products.id, Products.cost_price).where(
                Products.id.in_(pids),
                Products.client_id == client_id,
            )
        )
    ).all()
    cost_map = {pid: float(cost or 0.0) for pid, cost in rows}
    for it, d in zip(lines, line_dicts):
        if d.get("cost_price") is not None:
            continue
        pid = getattr(it, "product_id", None)
        if pid is not None and int(pid) in cost_map:
            d["cost_price"] = cost_map[int(pid)]


def persist_tenders(
    db: AsyncSession, user_id: str, client_id: int, txn_id: int, captured: List[dict]
) -> None:
    """Write the captured tender rows for a sale (links them to the transaction)."""
    for row in captured:
        db.add(
            PaymentTenders(
                user_id=user_id,
                client_id=client_id,
                transaction_id=txn_id,
                tender_type=row["tender_type"],
                amount=row["amount"],
                network=row["network"],
                approval_code=row["approval_code"],
                rrn=row["rrn"],
                gateway_ref=row["gateway_ref"],
                last4=row["last4"],
                token=row["token"],
                gateway=row["gateway"],
                status=row["status"],
                decline_reason=row["decline_reason"],
            )
        )


# ---------------------------------------------------------------------------
# The normalized cart + the one atomic sale path
# ---------------------------------------------------------------------------
@dataclass
class NormalizedCart:
    """Everything :func:`execute_sale` needs to mint one fiscal sale.

    ``lines`` are CartItem-like objects (anything exposing ``model_dump()`` plus
    ``product_id`` / ``quantity`` / ``variant_id``) — the POS handler, the
    restaurant settle path (F-059) and aggregator ingest (F-060) each normalize
    their own input into this shape. ``tender_specs`` are the per-leg capture specs
    (already validated to sum to the amount due, incl. tip + service charge). The
    monetary totals are authoritative and computed by the caller; the core does not
    re-derive VAT.
    """

    user_id: str
    client: Clients
    lines: List[Any]
    subtotal: float
    discount_amount: float
    vat_rate: float
    vat_amount: float
    total_amount: float
    tender_specs: List[dict] = field(default_factory=list)
    payment_method: str = "cash"
    payment_breakdown_json: Optional[str] = None
    # The discount code applied to the order (PRC-01), persisted onto the sale for
    # the discount report (F-071). Null for a manual override or no discount.
    discount_code: Optional[str] = None
    # Tip (POS-13/F-012) and service charge (F-061) both live OUTSIDE the VAT base —
    # they never change subtotal/VAT/total, only what the tenders must cover. The
    # caller folds them into ``tender_specs``; the core records the tip on the row.
    tip_amount: float = 0.0
    service_charge: float = 0.0
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    buyer_vat: Optional[str] = None
    branch_id: Optional[int] = None
    allow_negative_stock: bool = False
    offline_id: Optional[str] = None
    # F-062: when set, BOM-backed lines deplete their recipe components inside the
    # same atomic stock transaction (the restaurant settle path turns this on).
    expand_bom: bool = False
    # Loyalty accrual (Phase E): when a customer + active program are supplied the
    # core earns points on the total inside the sale transaction. ``loyalty_balance``
    # carries the post-redemption balance the handler already computed; the core
    # overwrites it with the post-accrual balance.
    loyalty_customer_id: Optional[int] = None
    loyalty_program: Any = None
    loyalty_balance: Optional[int] = None


@dataclass
class SaleResult:
    """The committed outcome of :func:`execute_sale`."""

    transaction: Transactions
    document_id: Optional[int]
    stamped_qr: Optional[str]
    captured_tenders: List[dict]
    loyalty_points_earned: int = 0
    loyalty_balance: Optional[int] = None


async def execute_sale(db: AsyncSession, cart: NormalizedCart) -> SaleResult:
    """Mint one fiscal sale atomically from a :class:`NormalizedCart`.

    Runs the full sequence — tender capture → invoice counter → inventory deduction
    (incl. BOM expansion) → loyalty accrual → shift accumulation → ECDSA sign /
    hash-chain / archive — in the caller's session and commits once. Any failure
    (a declined card, insufficient stock, a signing error) raises before commit so
    nothing is persisted: no orphan invoice, no consumed counter, no partial stock
    deduction (POS atomicity). Returns the persisted transaction + fiscal linkage.
    """
    client = cart.client
    user_id = cart.user_id

    # ---- Saudi-real tender capture (PAY-01/05) ----
    # Push every card-like tender to the gateway for a real approval BEFORE the
    # invoice counter is consumed or any row is written. A decline raises 402 here
    # and, since nothing has committed, the whole sale rolls back (F-001). A leg may
    # name an in-store SoftPOS terminal (HW-03/F-005) — resolved here to the paired
    # device. Gift-card legs (PRC-05/F-038) are validated + atomically decremented
    # FIRST, before any card is charged.
    await attach_terminal_gateways(db, user_id, cart.tender_specs)
    giftcard_tenders = await redeem_gift_cards(db, user_id, client.id, cart.tender_specs)
    captured_tenders = await capture_tenders(cart.tender_specs)
    captured_tenders.extend(giftcard_tenders)

    # ---- Invoice counter + number ----
    current_counter = (client.invoice_counter or 0) + 1
    await db.execute(
        update(Clients)
        .where(Clients.id == client.id)
        .values(invoice_counter=current_counter)
    )
    invoice_number = f"INV-{client.id:04d}-{current_counter:06d}"

    # Snapshot each line's product cost onto items_json (F-068) so the profit/
    # margin report has a stable historical cost basis. Additive only — the rest
    # of the atomic sale is unchanged.
    line_dicts = [item.model_dump() for item in cart.lines]
    await snapshot_cost_prices(db, client.id, cart.lines, line_dicts)
    items_json = json.dumps(line_dicts, ensure_ascii=False)

    transaction = Transactions(
        user_id=user_id,
        client_id=client.id,
        invoice_number=invoice_number,
        offline_id=cart.offline_id,
        subtotal=cart.subtotal,
        vat_amount=cart.vat_amount,
        discount_amount=cart.discount_amount,
        discount_code=cart.discount_code,
        total_amount=cart.total_amount,
        tip_amount=cart.tip_amount,
        payment_method=cart.payment_method,
        payment_breakdown=cart.payment_breakdown_json,
        status="completed",
        items_json=items_json,
        customer_name=cart.customer_name,
        customer_phone=cart.customer_phone,
        customer_vat_number=cart.buyer_vat,
        branch_id=cart.branch_id,
    )
    db.add(transaction)

    # ---- Atomic inventory deduction (same transaction as the sale) ----
    # The sale, the invoice-counter increment, and every stock decrement are
    # committed together. Variant lines (INV-04) decrement their own variant stock;
    # a branch-tagged sale draws from that branch's ledger; otherwise client-level
    # product quantity. BOM-backed lines (F-062) additionally deplete their recipe
    # components when ``expand_bom`` is set (the restaurant settle path).
    variant_items = [it for it in cart.lines if getattr(it, "variant_id", None)]
    product_items = [it for it in cart.lines if not getattr(it, "variant_id", None)]
    if variant_items:
        # A branch-tagged variant sale draws from that branch's variant ledger
        # (ISSUE-067); otherwise the variant's client-level façade quantity.
        if cart.branch_id:
            from services.variant_branch_stock import deduct_variant_branch_inventory

            await deduct_variant_branch_inventory(
                db, user_id, client.id, int(cart.branch_id), variant_items,
                bool(cart.allow_negative_stock),
            )
        else:
            from services.product_variants import deduct_variant_inventory

            await deduct_variant_inventory(
                db, client.id, variant_items, bool(cart.allow_negative_stock)
            )
    if cart.branch_id:
        from services.branch_stock import deduct_branch_inventory

        await deduct_branch_inventory(
            db,
            user_id,
            client.id,
            int(cart.branch_id),
            product_items,
            bool(cart.allow_negative_stock),
        )
    else:
        await deduct_inventory(
            db, client.id, product_items, bool(cart.allow_negative_stock)
        )
    if cart.expand_bom:
        await deduct_bom_components(
            db,
            user_id,
            client.id,
            [(getattr(it, "product_id", None), getattr(it, "quantity", 0)) for it in product_items],
            bool(cart.allow_negative_stock),
        )

    # ---- Loyalty accrual (Phase E) ----
    loyalty_points_earned = 0
    loyalty_balance = cart.loyalty_balance
    if cart.loyalty_customer_id and cart.loyalty_program:
        accrual = await loyalty_service.accrue_points(
            db,
            user_id=user_id,
            client_id=client.id,
            customer_id=cart.loyalty_customer_id,
            total_amount=cart.total_amount,
            program=cart.loyalty_program,
        )
        if accrual:
            loyalty_points_earned = accrual.points_earned
            loyalty_balance = accrual.new_balance

    # ---- Shift accumulation (POS shifts) ----
    transaction.shift_id = await apply_sale_to_open_shift(
        db, user_id, cart.total_amount
    )

    # ---- ZATCA signing on the real sale path (C-3) ----
    # Hash + ECDSA-stamp + hash-chain + archive inside this same transaction. A
    # signing failure raises and rolls the sale back. ZA-09: honor the per-client
    # zatca_enabled opt-out — with it off the sale completes as a simplified
    # non-tax receipt (no stamp/QR, no zatca_documents row).
    await db.flush()  # assign transaction.id before signing
    persist_tenders(db, user_id, client.id, transaction.id, captured_tenders)
    if zatca_sale.is_zatca_enabled(client):
        doc, stamped_qr = await zatca_sale.sign_transaction(
            db, client, transaction,
            buyer_vat=transaction.customer_vat_number,
        )
        document_id = doc.id
    else:
        stamped_qr = None
        document_id = None

    await db.commit()
    await db.refresh(transaction)

    return SaleResult(
        transaction=transaction,
        document_id=document_id,
        stamped_qr=stamped_qr,
        captured_tenders=captured_tenders,
        loyalty_points_earned=loyalty_points_earned,
        loyalty_balance=loyalty_balance,
    )
