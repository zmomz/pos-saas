import base64
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.auth import get_current_user
from dependencies.features import require_feature
from dependencies.permissions import has_permission, require_permission
from schemas.auth import UserResponse
from models.audit_logs import Audit_logs
from models.clients import Clients
from models.customers import Customers
from models.products import Products
from models.transactions import Transactions
from models.payment_tenders import PaymentTenders
from models.terminals import Terminals
from models.zatca_documents import ZatcaDocuments
# Imported so the per-branch stock table registers on Base.metadata at startup
# (services.branch_stock is only imported lazily inside handlers).
from models.product_branch_stock import Product_branch_stock  # noqa: F401
from services import loyalty as loyalty_service
from services.discounts import (
    DiscountsService,
    DiscountValidationError,
    compute_discount_amount,
)
from services.payment_gateway import (
    GatewayNotConfigured,
    PaymentDeclined,
    get_gateway,
    get_gateway_for,
    get_terminal_gateway,
    normalize_tender_type,
    requires_capture,
)
from services import zatca as zatca_service_mod
from services import zatca_sale
from services.escpos import build_receipt_base64
from services.production import EmailService, LowStockChecker, PDFInvoiceService, fire_event_background
from services.system_settings import get_effective_tax_rate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/pos", tags=["pos"])


# ---------- Pydantic Schemas ----------
class CartItem(BaseModel):
    product_id: int
    name: str
    # Arabic product name carried into items_json so the always-Arabic thermal
    # receipt prints the Arabic line name (PRN-01 / L10N-06, F-021). Optional —
    # falls back to ``name`` when absent.
    name_ar: Optional[str] = None
    price: float
    quantity: int
    discount: Optional[float] = 0


class PaymentEntry(BaseModel):
    """One tender line of a (possibly split) payment, e.g. cash + card."""

    method: str  # "cash", "card", "mada", "applepay", "stcpay", "tabby", "tamara", "transfer", "loyalty"
    amount: float
    # Saudi-real tender capture (PAY-01/05). When the tender is card-like the POS
    # asks the gateway for a real approval before the sale completes. ``token`` is
    # the gateway-side card token from client tokenization (no PAN reaches us —
    # PAY-09). ``simulate`` is a sandbox-only hint ("approve"/"decline") that real
    # gateways ignore. ``tender_type`` overrides ``method`` when the caller wants
    # the canonical type explicitly.
    tender_type: Optional[str] = None
    token: Optional[str] = None
    simulate: Optional[str] = None
    # In-store SoftPOS capture (HW-03/PAY-05, F-005). When set, this leg is pushed
    # to the named (owner-scoped) terminal for a real approval instead of the online
    # gateway; a decline blocks the whole sale.
    terminal_id: Optional[int] = None


class CreateTransactionRequest(BaseModel):
    items: List[CartItem]
    payment_method: str  # "cash", "card", "mixed"
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    # Buyer VAT registration number for a B2B sale (F-018 / ZA-06). When given (or
    # resolvable from ``customer_id``'s saved record) the invoice carries the buyer
    # tax block and routes to clearance once it clears the threshold. Optional —
    # ordinary B2C sales leave it unset.
    customer_vat_number: Optional[str] = None
    # PRC-01: a discount *code* the server validates and prices authoritatively.
    # When given, the server recomputes the order discount from the rule
    # (type/value/min-purchase/usage-cap) — ignoring any client-sent
    # ``discount_amount`` for the coded portion — and consumes one use atomically
    # with the sale. A raw ``discount_amount`` with no code is a manual override
    # gated behind the ``pos.discount`` permission.
    discount_code: Optional[str] = None
    discount_amount: Optional[float] = 0
    vat_rate: Optional[float] = 15.0  # fallback; the global rate (MA-05) wins when set
    # Optional split-tender breakdown (POS-02). When given, the per-method amounts
    # must sum to the invoice total; payment_method is derived ("mixed" if >1).
    payments: Optional[List[PaymentEntry]] = None
    # Loyalty (Phase E). When a customer is identified, points are accrued on the
    # sale; ``redeem_points`` redeems against their balance as an order discount.
    # Both move the loyalty ledger inside the same atomic transaction as the sale.
    customer_id: Optional[int] = None
    redeem_points: Optional[int] = 0
    # When False (default) a sale is rejected if any line exceeds available stock.
    # The sale and the stock deduction are committed together in one transaction.
    allow_negative_stock: Optional[bool] = False
    # Branch the sale is rung up at (multi-branch). Enables branch-scoped reports.
    branch_id: Optional[int] = None
    # Single-tender capture hints (used when ``payments`` is not given): the
    # gateway card token from client-side tokenization, and a sandbox-only
    # simulate hint ("approve"/"decline").
    payment_token: Optional[str] = None
    payment_simulate: Optional[str] = None
    # In-store SoftPOS terminal for a single card-like tender (HW-03/PAY-05). When
    # set, the card leg is captured on this owner-scoped terminal; a decline blocks
    # the sale.
    payment_terminal_id: Optional[int] = None


class TenderInfo(BaseModel):
    """A captured tender on the sale (PAY-01). Carries only PCI-safe fields."""

    tender_type: str
    amount: float
    network: Optional[str] = None
    approval_code: Optional[str] = None
    rrn: Optional[str] = None
    last4: Optional[str] = None
    gateway: Optional[str] = None
    status: str = "captured"


class TransactionResponse(BaseModel):
    id: int
    invoice_number: str
    subtotal: float
    vat_amount: float
    discount_amount: float
    total_amount: float
    payment_method: str
    payment_breakdown: Optional[str] = None
    status: str
    # zatca_qr is the **stamped** ZATCA TLV (base64); zatca_qr_base64 is the
    # ready-to-render QR PNG (base64) the frontend shows directly (C-4).
    zatca_qr: Optional[str] = None
    zatca_qr_base64: Optional[str] = None
    zatca_hash: Optional[str] = None
    # Fiscal document linkage + reporting state for this sale (C-3).
    zatca_document_id: Optional[int] = None
    zatca_status: Optional[str] = None
    items_json: Optional[str] = None
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    created_at: Optional[datetime] = None
    # Loyalty outcome of this sale (Phase E); null when no customer/program.
    loyalty_points_earned: Optional[int] = None
    loyalty_points_redeemed: Optional[int] = None
    loyalty_discount: Optional[float] = None
    loyalty_balance: Optional[int] = None
    # Captured tenders (PAY-01): the network/approval proof for each card-like
    # tender, so the receipt can show how the sale was really paid.
    tenders: Optional[List[TenderInfo]] = None


class TransactionListResponse(BaseModel):
    items: List[TransactionResponse]
    total: int
    page: int
    page_size: int


# ---------- ZATCA QR Helper ----------
def generate_zatca_tlv(
    seller_name: str,
    vat_number: str,
    timestamp: str,
    total_with_vat: str,
    vat_amount: str,
) -> str:
    """
    Generate ZATCA-compliant QR code data using TLV (Tag-Length-Value) encoding.
    Tags:
      1 = Seller Name
      2 = VAT Registration Number
      3 = Timestamp (ISO 8601)
      4 = Invoice Total (with VAT)
      5 = VAT Amount
    Each TLV: 1 byte tag + 1 byte length + value bytes (UTF-8)
    Result is base64 encoded.
    """
    tlv_data = bytearray()

    fields = [
        (1, seller_name),
        (2, vat_number),
        (3, timestamp),
        (4, total_with_vat),
        (5, vat_amount),
    ]

    for tag, value in fields:
        value_bytes = value.encode("utf-8")
        tlv_data.append(tag)
        tlv_data.append(len(value_bytes))
        tlv_data.extend(value_bytes)

    return base64.b64encode(bytes(tlv_data)).decode("utf-8")


def generate_zatca_hash(invoice_data: dict) -> str:
    """Generate SHA-256 hash of the invoice data for integrity verification."""
    data_str = json.dumps(invoice_data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(data_str.encode("utf-8")).hexdigest()


# ---------- Helper: Atomic inventory deduction ----------
async def _deduct_inventory(
    db: AsyncSession,
    client_id: int,
    items: List["CartItem"],
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
    requested: dict[int, int] = {}
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


# ---------- Helper: accumulate a sale into the open shift ----------
async def _apply_sale_to_open_shift(
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


# ---------- Helper: Saudi-real tender capture (PAY-01/05) ----------
async def _capture_tenders(specs: List[dict]) -> List[dict]:
    """Capture each tender via the active gateway, returning persistable rows.

    For a card-like tender (card/mada/applepay/stcpay/tabby/tamara) the gateway is
    asked for a real approval; a decline (or an unconfigured real gateway) raises
    ``HTTPException(402)``. Because the caller is mid-transaction and has not
    committed, that raise rolls the whole sale back — a declined card never leaves
    a persisted sale (F-001). Cash/transfer/loyalty settle internally and are
    recorded without a gateway round-trip.

    Each spec is ``{tender_type|method, amount, token, simulate, _gateway?}``. A
    spec may carry a pre-resolved ``_gateway`` (an in-store SoftPOS terminal — set
    by :func:`_attach_terminal_gateways`); otherwise the active online/sandbox
    gateway captures it.
    """
    default_gateway = get_gateway()
    captured: List[dict] = []
    for spec in specs:
        gateway = spec.get("_gateway") or default_gateway
        ttype = normalize_tender_type(spec.get("tender_type") or spec.get("method"))
        amount = round(float(spec.get("amount") or 0), 2)
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


def _build_tender_specs(data: "CreateTransactionRequest", total_amount: float) -> List[dict]:
    """Derive the per-tender capture specs from a sale request (split or single)."""
    if data.payments:
        return [
            {
                "tender_type": p.tender_type or p.method,
                "amount": p.amount,
                "token": p.token,
                "simulate": p.simulate,
                "terminal_id": p.terminal_id,
            }
            for p in data.payments
        ]
    return [
        {
            "tender_type": data.payment_method,
            "amount": total_amount,
            "token": data.payment_token,
            "simulate": data.payment_simulate,
            "terminal_id": data.payment_terminal_id,
        }
    ]


async def _attach_terminal_gateways(
    db: AsyncSession, user_id: str, specs: List[dict]
) -> None:
    """Resolve an in-store SoftPOS terminal for any spec that names one (HW-03/F-005).

    For each spec carrying a ``terminal_id``, verify the terminal belongs to the
    caller (SEC-02) and is active, then attach its provider's gateway as
    ``spec["_gateway"]`` so :func:`_capture_tenders` pushes that leg to the paired
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


def _persist_tenders(
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


# ---------- Helper: Saudi-real refund-to-origin (PAY-10, F-004) ----------
async def _refund_tenders(
    db: AsyncSession,
    original: Transactions,
    refund_amount: float,
) -> List[dict]:
    """Route a refund back to the original sale's tenders (PAY-10, F-004).

    Allocates ``refund_amount`` across the original sale's captured tenders in
    proportion to each leg's share of that sale, and for every **card-like** leg
    calls the **capturing** gateway's ``refund`` so the money is actually reversed
    to origin — a card/Mada refund goes back to the card, not the drawer. Each
    reversed leg becomes a ``refunded`` tender row (persisted by the caller against
    the credit note) carrying the gateway refund reference, so the reversal is
    auditable and the drawer reconciliation can separate the cash portion of a
    refund from the card portion.

    A gateway refund failure raises ``HTTPException(502)`` so the whole credit note
    rolls back (mirrors the capture-decline rollback on the sale path). Cash /
    transfer / loyalty legs settle internally (no gateway round-trip) but are still
    recorded. A legacy sale captured before tender capture (F-001) has no tender
    rows to route to and returns ``[]`` — the credit note then nets the drawer as
    cash out via the legacy fallback in ``compute_shift_cash_reconciliation``.

    Returns the persistable ``refunded`` tender rows (possibly empty).
    """
    if refund_amount <= 0:
        return []
    original_tenders = (
        await db.execute(
            select(PaymentTenders).where(
                PaymentTenders.transaction_id == original.id,
                PaymentTenders.status.in_(("captured", "authorized")),
            )
        )
    ).scalars().all()
    if not original_tenders:
        return []

    captured_sum = sum(float(t.amount or 0) for t in original_tenders)
    rows: List[dict] = []
    for ot in original_tenders:
        share = (float(ot.amount or 0) / captured_sum) if captured_sum else 0.0
        leg_amount = round(refund_amount * share, 2)
        if leg_amount <= 0:
            continue
        row = {
            "tender_type": ot.tender_type,
            "amount": leg_amount,
            "gateway": ot.gateway,
            "status": "refunded",
            "network": ot.network,
            "approval_code": None,
            "rrn": ot.rrn,
            "gateway_ref": ot.gateway_ref,
            "last4": ot.last4,
            "token": ot.token,
            "decline_reason": None,
        }
        if requires_capture(ot.tender_type) and ot.gateway_ref:
            gateway = get_gateway_for(ot.gateway)
            try:
                result = await gateway.refund(ot.gateway_ref, leg_amount)
            except GatewayNotConfigured as exc:
                logger.warning(
                    "Refund-to-origin not configured for %s: %s", ot.tender_type, exc
                )
                raise HTTPException(status_code=502, detail=f"Refund not processed: {exc}")
            except PaymentDeclined as exc:
                logger.info(
                    "Refund for %s declined by %s: %s", ot.tender_type, exc.gateway, exc.reason
                )
                raise HTTPException(status_code=502, detail=f"Refund declined: {exc.reason}")
            if not result.approved:
                raise HTTPException(
                    status_code=502,
                    detail=f"Refund declined for {ot.tender_type}: {result.decline_reason or 'declined'}",
                )
            row.update(
                gateway=result.gateway or ot.gateway,
                approval_code=result.approval_code,
                gateway_ref=result.gateway_ref or ot.gateway_ref,
            )
        rows.append(row)
    return rows


# ---------- Helper: Get client for current user ----------
async def get_client_for_user(db: AsyncSession, user_id: str) -> Clients:
    """Get the client record for the current user."""
    result = await db.execute(
        select(Clients).where(Clients.user_id == user_id)
    )
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=403, detail="Only clients can access POS features")
    return client


# ---------- Endpoints ----------
@router.post("/transaction", response_model=TransactionResponse)
async def create_transaction(
    data: CreateTransactionRequest,
    background_tasks: BackgroundTasks,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new POS transaction, ECDSA-signed and ZATCA-reported (C-3/C-4)."""
    client = await get_client_for_user(db, str(current_user.id))

    # Calculate totals
    subtotal = 0.0
    for item in data.items:
        item_total = item.price * item.quantity - (item.discount or 0)
        subtotal += item_total

    # ---- Price override (POS-08): gate manual unit-price changes (SEC-07) ----
    # A cart line whose unit price differs from the product's catalog price is a
    # manual price override — a fraud-sensitive action. Like the manual discount
    # below it is permissioned: the account owner holds ``pos.price_override`` by
    # default (deny-wins), but a restricted cashier can be denied, in which case an
    # overridden line is rejected before anything is written. Ad-hoc lines whose
    # ``product_id`` doesn't map to a catalog product are left to the cashier.
    override_pids = [it.product_id for it in data.items if it.product_id]
    if override_pids:
        catalog_prices = {
            row.id: float(row.price or 0)
            for row in (
                await db.execute(
                    select(Products.id, Products.price).where(
                        Products.id.in_(override_pids),
                        Products.client_id == client.id,
                    )
                )
            ).all()
        }
        has_override = any(
            it.product_id in catalog_prices
            and abs(float(it.price) - catalog_prices[it.product_id]) > 0.001
            for it in data.items
        )
        if has_override and not await has_permission(
            db, str(current_user.id), "pos.price_override"
        ):
            raise HTTPException(
                status_code=403,
                detail="You do not have the 'pos.price_override' permission.",
            )

    # ---- Discount (PRC-01): validate server-side; never trust the client amount ----
    # A coded discount is validated against the order subtotal and priced from the
    # rule (type/value/min-purchase/usage-cap); one use is then consumed atomically
    # with the sale, so a rolled-back sale never spends a use and concurrent sales
    # cannot exceed ``max_uses``. A raw ``discount_amount`` with no code is a manual
    # override and requires the ``pos.discount`` permission (deny-wins; the account
    # owner has it by default, a restricted cashier can be denied).
    discounts_service = DiscountsService(db)
    discount_code = (data.discount_code or "").strip()
    if discount_code:
        try:
            discount_rule = await discounts_service.validate(
                discount_code, subtotal, user_id=str(current_user.id)
            )
        except DiscountValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        discount_amount = compute_discount_amount(discount_rule, subtotal)
        if not await discounts_service.consume(
            discount_rule.id, user_id=str(current_user.id)
        ):
            # Lost the cap race between validate and consume — treat as exhausted.
            raise HTTPException(
                status_code=400, detail="This discount has reached its usage limit"
            )
    else:
        discount_amount = round(float(data.discount_amount or 0), 2)
        if discount_amount > 0 and not await has_permission(
            db, str(current_user.id), "pos.discount"
        ):
            raise HTTPException(
                status_code=403,
                detail="You do not have the 'pos.discount' permission.",
            )

    # ---- Loyalty redemption (Phase E) ----
    # Redeemed points reduce the order as a discount (before VAT). The point
    # deduction happens in this same session and is committed atomically with
    # the sale below, so a rolled-back sale never spends points.
    program = await loyalty_service.get_active_program(db, str(current_user.id))
    loyalty_points_redeemed = 0
    loyalty_discount = 0.0
    loyalty_balance: Optional[int] = None
    if data.redeem_points and data.redeem_points > 0:
        if not data.customer_id:
            raise HTTPException(
                status_code=400,
                detail="customer_id is required to redeem loyalty points",
            )
        if not program:
            raise HTTPException(
                status_code=400, detail="No active loyalty program configured"
            )
        try:
            redemption = await loyalty_service.redeem_points(
                db,
                user_id=str(current_user.id),
                client_id=client.id,
                customer_id=data.customer_id,
                points=int(data.redeem_points),
                program=program,
                max_discount=round(subtotal - discount_amount, 2),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        loyalty_points_redeemed = redemption.points_redeemed
        loyalty_discount = redemption.discount_value
        loyalty_balance = redemption.remaining_balance
        discount_amount = round(discount_amount + redemption.discount_value, 2)

    taxable_amount = subtotal - discount_amount
    # MA-05: the master's global VAT rate is authoritative; the request rate is
    # only a fallback for installs with no global rate configured.
    vat_rate = await get_effective_tax_rate(db, data.vat_rate)
    vat_amount = round(taxable_amount * (vat_rate / 100), 2)
    total_amount = round(taxable_amount + vat_amount, 2)

    # ---- Payment breakdown (POS-02): validate + summarise split tenders ----
    payment_breakdown_json: Optional[str] = None
    payment_method = data.payment_method
    if data.payments:
        paid_total = round(sum(p.amount for p in data.payments), 2)
        if abs(paid_total - total_amount) > 0.01:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Payment breakdown total {paid_total:.2f} does not match "
                    f"invoice total {total_amount:.2f}"
                ),
            )
        payment_breakdown_json = json.dumps(
            [p.model_dump() for p in data.payments], ensure_ascii=False
        )
        methods = [p.method for p in data.payments]
        payment_method = "mixed" if len(set(methods)) > 1 else methods[0]

    # ---- Saudi-real tender capture (PAY-01/05) ----
    # Push every card-like tender to the gateway for a real approval BEFORE the
    # invoice counter is consumed or any row is written. A decline raises 402 here
    # and, since nothing has committed, the whole sale rolls back — a "Mada"/card
    # sale can no longer complete without proof it was charged (F-001). Cash and
    # internal tenders pass through with no gateway round-trip. A leg may name an
    # in-store SoftPOS terminal (HW-03/F-005) — resolved here to the paired device
    # so the customer taps and the approval is captured before any row is written.
    tender_specs = _build_tender_specs(data, total_amount)
    await _attach_terminal_gateways(db, str(current_user.id), tender_specs)
    captured_tenders = await _capture_tenders(tender_specs)

    # Increment invoice counter
    current_counter = (client.invoice_counter or 0) + 1
    await db.execute(
        update(Clients)
        .where(Clients.id == client.id)
        .values(invoice_counter=current_counter)
    )

    # Generate invoice number
    invoice_number = f"INV-{client.id:04d}-{current_counter:06d}"

    # Generate timestamp
    now = datetime.now(timezone.utc)
    timestamp_iso = now.isoformat()

    # Serialize items
    items_json = json.dumps(
        [item.model_dump() for item in data.items],
        ensure_ascii=False,
    )

    # ---- Buyer VAT capture (F-018 / ZA-06) ----
    # A VAT-registered buyer makes this a B2B supply. Prefer the explicit request
    # value (ad-hoc business walk-in); otherwise fall back to the saved customer's
    # VAT number (trusted record, scoped to this user). The captured number is
    # stamped onto the transaction so the invoice buyer block and the
    # clearance/reporting routing are driven by it (see sign_transaction below).
    buyer_vat = (data.customer_vat_number or "").strip() or None
    if not buyer_vat and data.customer_id:
        cust = (
            await db.execute(
                select(Customers).where(
                    Customers.id == data.customer_id,
                    Customers.user_id == str(current_user.id),
                )
            )
        ).scalar_one_or_none()
        if cust and (cust.vat_number or "").strip():
            buyer_vat = cust.vat_number.strip()

    # Create transaction record. The fiscal QR/hash are populated by signing
    # below (C-3) — never with the old unsigned Phase-1 TLV.
    transaction = Transactions(
        user_id=str(current_user.id),
        client_id=client.id,
        invoice_number=invoice_number,
        subtotal=subtotal,
        vat_amount=vat_amount,
        discount_amount=discount_amount,
        total_amount=total_amount,
        payment_method=payment_method,
        payment_breakdown=payment_breakdown_json,
        status="completed",
        items_json=items_json,
        customer_name=data.customer_name,
        customer_phone=data.customer_phone,
        customer_vat_number=buyer_vat,
        branch_id=data.branch_id,
    )
    db.add(transaction)

    # ---- Atomic inventory deduction (same transaction as the sale) ----
    # The sale, the invoice-counter increment, and every stock decrement are
    # committed together. If stock is insufficient (and overselling isn't
    # allowed) we raise before commit, so nothing is persisted and the counter
    # is not consumed — fixing the previous fire-and-forget deduction gap.
    #
    # Multi-branch (Phase 6): when the sale is tagged with a branch_id, deduct
    # from that branch's stock ledger so a sale in branch A never touches branch
    # B's stock. Otherwise fall back to client-level product quantity.
    if data.branch_id:
        from services.branch_stock import deduct_branch_inventory

        await deduct_branch_inventory(
            db,
            str(current_user.id),
            client.id,
            int(data.branch_id),
            data.items,
            bool(data.allow_negative_stock),
        )
    else:
        await _deduct_inventory(db, client.id, data.items, bool(data.allow_negative_stock))

    # ---- Loyalty accrual (Phase E) ----
    # Earn points for the identified customer on the final total, in the same
    # transaction as the sale. Runs after any redemption so the returned balance
    # reflects both movements.
    loyalty_points_earned = 0
    if data.customer_id and program:
        accrual = await loyalty_service.accrue_points(
            db,
            user_id=str(current_user.id),
            client_id=client.id,
            customer_id=data.customer_id,
            total_amount=total_amount,
            program=program,
        )
        if accrual:
            loyalty_points_earned = accrual.points_earned
            loyalty_balance = accrual.new_balance

    # ---- Shift accumulation (POS shifts) ----
    # Roll this sale into the cashier's open shift so close_shift reconciles cash
    # against real sales. Linked via shift_id; committed atomically with the sale.
    transaction.shift_id = await _apply_sale_to_open_shift(
        db, str(current_user.id), total_amount
    )

    # ---- ZATCA signing on the real sale path (C-3) ----
    # Hash + ECDSA-stamp + hash-chain + archive the invoice inside this same
    # transaction. A signing failure raises and rolls the sale back, so a
    # completed sale is never silently left unsigned.
    await db.flush()  # assign transaction.id before signing
    # Persist the captured tenders against the now-known transaction id. These
    # carry the real network/approval/RRN proof for card-like tenders (PAY-01).
    _persist_tenders(db, str(current_user.id), client.id, transaction.id, captured_tenders)
    # ZA-06: a VAT-registered buyer on the transaction routes the invoice to B2B
    # clearance; the captured buyer VAT (F-018) is rendered into the UBL buyer block.
    doc, stamped_qr = await zatca_sale.sign_transaction(
        db, client, transaction,
        buyer_vat=transaction.customer_vat_number,
    )
    document_id = doc.id

    await db.commit()
    await db.refresh(transaction)

    # Queue Fatoora reporting out-of-band (C-3): fails closed to "pending" when
    # the gateway/onboarding isn't configured; never blocks the committed sale.
    background_tasks.add_task(
        zatca_sale.report_document_background, document_id, client.id
    )

    # ---- Domain webhook: sale.completed (Phase 3) ----
    # Fire registered webhooks out-of-band so integrations (accounting, ERP) are
    # notified. Best-effort: a failing endpoint never affects the committed sale.
    background_tasks.add_task(
        fire_event_background,
        str(current_user.id),
        "sale.completed",
        {
            "transaction_id": transaction.id,
            "invoice_number": transaction.invoice_number,
            "total_amount": transaction.total_amount,
            "client_id": client.id,
        },
    )

    # ---- Automated low-stock alerts (best-effort, post-commit) ----
    # After the sale is durably persisted, notify the merchant about any sold
    # product that has fallen to/below the threshold. Never blocks or fails the
    # sale — alert dispatch is in stub/log mode until SMTP is configured.
    await _maybe_send_low_stock_alerts(db, client, data.items)

    return TransactionResponse(
        id=transaction.id,
        invoice_number=transaction.invoice_number,
        subtotal=transaction.subtotal or 0,
        vat_amount=transaction.vat_amount or 0,
        discount_amount=transaction.discount_amount or 0,
        total_amount=transaction.total_amount,
        payment_method=transaction.payment_method,
        payment_breakdown=transaction.payment_breakdown,
        status=transaction.status or "completed",
        zatca_qr=stamped_qr,
        zatca_qr_base64=zatca_service_mod.render_qr_png_base64(stamped_qr),
        zatca_hash=transaction.zatca_hash,
        zatca_document_id=document_id,
        zatca_status="signed",
        items_json=transaction.items_json,
        customer_name=transaction.customer_name,
        customer_phone=transaction.customer_phone,
        created_at=transaction.created_at,
        loyalty_points_earned=loyalty_points_earned or None,
        loyalty_points_redeemed=loyalty_points_redeemed or None,
        loyalty_discount=loyalty_discount or None,
        loyalty_balance=loyalty_balance,
        tenders=[
            TenderInfo(
                tender_type=row["tender_type"],
                amount=row["amount"],
                network=row["network"],
                approval_code=row["approval_code"],
                rrn=row["rrn"],
                last4=row["last4"],
                gateway=row["gateway"],
                status=row["status"],
            )
            for row in captured_tenders
        ]
        or None,
    )


async def _maybe_send_low_stock_alerts(
    db: AsyncSession, client: Clients, items: List["CartItem"]
) -> None:
    """Dispatch a low-stock alert for any sold product now at/below threshold."""
    threshold = LowStockChecker.DEFAULT_THRESHOLD
    product_ids = list({item.product_id for item in items})
    if not product_ids:
        return
    try:
        result = await db.execute(
            select(Products).where(
                Products.client_id == client.id,
                Products.id.in_(product_ids),
                Products.quantity <= threshold,
                Products.is_active == True,  # noqa: E712
            )
        )
        for product in result.scalars().all():
            await EmailService.send_low_stock_alert(
                to_email=client.email,
                product_name=product.name,
                current_stock=product.quantity or 0,
                threshold=threshold,
            )
    except Exception as exc:  # pragma: no cover - alerts must never break a sale
        logger.warning("Low-stock alert dispatch failed: %s", exc)


# ---------- Offline sync: route a queued sale through the full atomic path ----------
async def process_offline_sale(
    db: AsyncSession, user_id: str, client_id: int, txn: dict
) -> dict:
    """Persist one offline-queued sale through the **same** atomic path as a live
    sale (POS-05): invoice counter, inventory deduction, shift accumulation, and
    ECDSA signing + hash-chaining — committed together.

    Deduplicates by the client-generated ``offline_id`` so re-syncing the same
    queue never double-books. Returns ``{"status": "processed"|"skipped",
    "transaction_id": int|None, "invoice_number": str|None}``.
    """
    offline_id = txn.get("offline_id")
    if offline_id:
        existing = await db.execute(
            select(Transactions).where(
                Transactions.user_id == user_id,
                Transactions.offline_id == offline_id,
            )
        )
        if existing.scalar_one_or_none():
            return {"status": "skipped", "transaction_id": None, "invoice_number": None}

    # Re-fetch the client each call so invoice_counter/chain state is current
    # after the previous queued sale committed.
    client = (
        await db.execute(select(Clients).where(Clients.id == client_id))
    ).scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=403, detail="Unknown client for offline sale")

    raw_items = txn.get("items") or []
    items = [
        CartItem(
            product_id=int(it.get("product_id")),
            name=str(it.get("name") or "Item"),
            price=float(it.get("price") or 0),
            quantity=int(it.get("quantity") or 0),
            discount=float(it.get("discount") or 0),
        )
        for it in raw_items
        if it.get("product_id") is not None
    ]

    # Recompute totals from the line items (authoritative), mirroring the live path.
    subtotal = sum(i.price * i.quantity - (i.discount or 0) for i in items)
    discount_amount = float(txn.get("discount_amount") or 0)
    taxable_amount = subtotal - discount_amount
    vat_rate = await get_effective_tax_rate(db, 15.0)
    vat_amount = round(taxable_amount * (vat_rate / 100), 2)
    total_amount = round(taxable_amount + vat_amount, 2)

    current_counter = (client.invoice_counter or 0) + 1
    await db.execute(
        update(Clients).where(Clients.id == client.id).values(invoice_counter=current_counter)
    )
    invoice_number = f"INV-{client.id:04d}-{current_counter:06d}"

    transaction = Transactions(
        user_id=user_id,
        client_id=client.id,
        invoice_number=invoice_number,
        offline_id=offline_id,
        subtotal=subtotal,
        vat_amount=vat_amount,
        discount_amount=discount_amount,
        total_amount=total_amount,
        payment_method=txn.get("payment_method") or "cash",
        status="completed",
        items_json=json.dumps([i.model_dump() for i in items], ensure_ascii=False),
        customer_name=txn.get("customer_name"),
        customer_phone=txn.get("customer_phone"),
        customer_vat_number=(txn.get("customer_vat_number") or "").strip() or None,
    )
    db.add(transaction)

    await _deduct_inventory(db, client.id, items, bool(txn.get("allow_negative_stock")))
    transaction.shift_id = await _apply_sale_to_open_shift(db, user_id, total_amount)

    await db.flush()
    # Record the tender for the queued sale. Offline sales are cash or were
    # captured on-device, so we do not re-charge a gateway here — we persist the
    # recorded method so the tender ledger stays consistent with online sales.
    _persist_tenders(
        db,
        user_id,
        client.id,
        transaction.id,
        [
            {
                "tender_type": normalize_tender_type(transaction.payment_method),
                "amount": total_amount,
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
        ],
    )
    doc, _stamped_qr = await zatca_sale.sign_transaction(
        db, client, transaction,
        buyer_vat=transaction.customer_vat_number,
    )
    await db.commit()
    await db.refresh(transaction)
    return {
        "status": "processed",
        "transaction_id": transaction.id,
        "invoice_number": transaction.invoice_number,
    }


@router.get("/transactions", response_model=TransactionListResponse)
async def list_transactions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    branch_id: Optional[int] = Query(None, description="Filter to one branch (multi-branch)"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List transactions for the current client, optionally scoped to a branch."""
    client = await get_client_for_user(db, str(current_user.id))

    offset = (page - 1) * page_size

    # POS-10: parked (held) tickets are not completed sales — keep them out of the
    # transaction history / refund picker. ``is_distinct_from`` excludes "held"
    # while still keeping rows whose status is NULL (legacy completed sales).
    filters = [
        Transactions.client_id == client.id,
        Transactions.status.is_distinct_from("held"),
    ]
    if branch_id is not None:
        filters.append(Transactions.branch_id == branch_id)

    # Get total count
    count_result = await db.execute(
        select(func.count(Transactions.id)).where(*filters)
    )
    total = count_result.scalar() or 0

    # Get paginated transactions
    result = await db.execute(
        select(Transactions)
        .where(*filters)
        .order_by(Transactions.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    transactions = result.scalars().all()

    items = [
        TransactionResponse(
            id=t.id,
            invoice_number=t.invoice_number,
            subtotal=t.subtotal or 0,
            vat_amount=t.vat_amount or 0,
            discount_amount=t.discount_amount or 0,
            total_amount=t.total_amount,
            payment_method=t.payment_method,
            payment_breakdown=t.payment_breakdown,
            status=t.status or "completed",
            zatca_qr=t.zatca_qr,
            zatca_hash=t.zatca_hash,
            items_json=t.items_json,
            customer_name=t.customer_name,
            customer_phone=t.customer_phone,
            created_at=t.created_at,
        )
        for t in transactions
    ]

    return TransactionListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


# ---------- Hold / Recall (park a sale) — POS-10 ----------
class HoldRequest(BaseModel):
    """Park the current cart as a held ticket so the sale can be resumed later.

    A held ticket runs NONE of the atomic-sale side effects: no invoice counter is
    consumed, no ZATCA stamp is issued, inventory is not deducted, no shift/loyalty
    movement. It is purely a saved cart the cashier can recall. Multiple concurrent
    held tickets are allowed; ``label`` (e.g. "Table 5", a customer name) tells them
    apart on recall.
    """

    items: List[CartItem]
    label: Optional[str] = None
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    branch_id: Optional[int] = None


class HeldTicketResponse(BaseModel):
    id: int
    label: Optional[str] = None
    item_count: int
    subtotal: float
    total_amount: float
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    branch_id: Optional[int] = None
    items_json: Optional[str] = None
    created_at: Optional[datetime] = None


class HeldListResponse(BaseModel):
    items: List[HeldTicketResponse]
    total: int


class RecallResponse(BaseModel):
    """The recalled cart contents, so the POS can repopulate and ring it up."""

    id: int
    label: Optional[str] = None
    items: List[CartItem]
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    branch_id: Optional[int] = None


def _held_summary(t: Transactions) -> HeldTicketResponse:
    try:
        items = json.loads(t.items_json) if t.items_json else []
    except (json.JSONDecodeError, TypeError):
        items = []
    return HeldTicketResponse(
        id=t.id,
        label=t.hold_label,
        item_count=sum(int(i.get("quantity", 0) or 0) for i in items),
        subtotal=t.subtotal or 0,
        total_amount=t.total_amount or 0,
        customer_name=t.customer_name,
        customer_phone=t.customer_phone,
        branch_id=t.branch_id,
        items_json=t.items_json,
        created_at=t.created_at,
    )


@router.post("/hold", response_model=HeldTicketResponse)
async def hold_sale(
    data: HoldRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Park the current cart as a ``held`` ticket (POS-10).

    Persists the cart so the cashier can serve another customer and resume this
    one later. No fiscal side effects: the invoice counter is untouched, no ZATCA
    stamp is issued, and stock is not deducted (that all happens when the recalled
    ticket is rung up through ``POST /pos/transaction``).
    """
    logger.info("hold_sale: user=%s items=%d", current_user.id, len(data.items))
    client = await get_client_for_user(db, str(current_user.id))

    if not data.items:
        raise HTTPException(status_code=400, detail="Cannot hold an empty cart")

    # Compute a display subtotal/total for the held-ticket list. The amounts are
    # informational only — the authoritative totals are recomputed on checkout.
    subtotal = 0.0
    for item in data.items:
        subtotal += item.price * item.quantity - (item.discount or 0)
    subtotal = round(subtotal, 2)
    vat_rate = await get_effective_tax_rate(db, 15.0)
    vat_amount = round(subtotal * (vat_rate / 100), 2)
    total_amount = round(subtotal + vat_amount, 2)

    # A held ticket consumes NO invoice counter — give it a clearly non-fiscal
    # placeholder number so it never collides with a real INV-/CRN- sequence.
    held_number = f"HELD-{client.id:04d}-{uuid.uuid4().hex[:8]}"

    held = Transactions(
        user_id=str(current_user.id),
        client_id=client.id,
        invoice_number=held_number,
        subtotal=subtotal,
        vat_amount=vat_amount,
        discount_amount=0,
        total_amount=total_amount,
        payment_method="held",
        status="held",
        hold_label=(data.label or "").strip() or None,
        items_json=json.dumps([i.model_dump() for i in data.items], ensure_ascii=False),
        customer_name=data.customer_name,
        customer_phone=data.customer_phone,
        branch_id=data.branch_id,
    )
    db.add(held)
    await db.commit()
    await db.refresh(held)
    return _held_summary(held)


@router.get("/held", response_model=HeldListResponse)
async def list_held_sales(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List the current client's parked (held) tickets, newest first (POS-10)."""
    client = await get_client_for_user(db, str(current_user.id))
    result = await db.execute(
        select(Transactions)
        .where(
            Transactions.client_id == client.id,
            Transactions.user_id == str(current_user.id),
            Transactions.status == "held",
        )
        .order_by(Transactions.created_at.desc())
    )
    held = result.scalars().all()
    return HeldListResponse(items=[_held_summary(t) for t in held], total=len(held))


@router.post("/recall/{held_id}", response_model=RecallResponse)
async def recall_sale(
    held_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Recall a held ticket: return its cart and remove it from the held list.

    The cashier resumes the cart in the POS and rings it up as a fresh sale, so the
    held row is deleted here (not flipped to a sale) — the sale is created normally
    via ``POST /pos/transaction`` with all its fiscal side effects. Owner-scoped: a
    client can only recall its own held tickets (SEC-02).
    """
    client = await get_client_for_user(db, str(current_user.id))
    result = await db.execute(
        select(Transactions).where(
            Transactions.id == held_id,
            Transactions.client_id == client.id,
            Transactions.user_id == str(current_user.id),
            Transactions.status == "held",
        )
    )
    held = result.scalar_one_or_none()
    if not held:
        raise HTTPException(status_code=404, detail="Held ticket not found")

    try:
        raw_items = json.loads(held.items_json) if held.items_json else []
    except (json.JSONDecodeError, TypeError):
        raw_items = []
    items = [CartItem(**i) for i in raw_items]

    response = RecallResponse(
        id=held.id,
        label=held.hold_label,
        items=items,
        customer_name=held.customer_name,
        customer_phone=held.customer_phone,
        branch_id=held.branch_id,
    )

    # Remove the parked ticket — it has been pulled back into the cart.
    await db.delete(held)
    await db.commit()
    return response


# ---------- Refund / ZATCA credit note (POS-07) ----------
class RefundLine(BaseModel):
    """One line to return on a partial/line-level refund (POS-07).

    ``quantity`` is how many units of ``product_id`` to credit; it must not exceed
    the units still un-refunded on the original invoice. Omit the whole ``lines``
    list to refund the entire remaining balance (the legacy whole-invoice refund).
    """

    product_id: int
    quantity: float


class RefundRequest(BaseModel):
    lines: Optional[List[RefundLine]] = None


class RefundResponse(BaseModel):
    credit_note_id: int
    original_transaction_id: int
    credit_note_number: str
    total_amount: float
    zatca_qr: Optional[str] = None
    zatca_qr_base64: Optional[str] = None
    zatca_document_id: int
    zatca_status: str
    # POS-07: "refunded" when every line is now fully returned, "partial_refunded"
    # when a balance remains on the original invoice.
    original_status: str = "refunded"


async def _refunded_quantities(db: AsyncSession, original_id: int) -> dict:
    """Sum already-refunded quantities per product across prior credit notes that
    reference ``original_id`` (POS-07). Lets a second partial refund see what the
    first one already returned so the invoice can never be over-refunded."""
    rows = (
        await db.execute(
            select(Transactions).where(
                Transactions.original_transaction_id == original_id,
                Transactions.status == "credit_note",
            )
        )
    ).scalars().all()
    refunded: dict[int, float] = {}
    for cn in rows:
        try:
            cn_items = json.loads(cn.items_json) if cn.items_json else []
        except (ValueError, TypeError):
            cn_items = []
        for it in cn_items:
            pid = it.get("product_id")
            if pid is None:
                continue
            refunded[int(pid)] = refunded.get(int(pid), 0.0) + float(it.get("quantity") or 0)
    return refunded


async def _restore_inventory(db: AsyncSession, client_id: int, items: List[dict]) -> None:
    """Add refunded quantities back to stock (inverse of ``_deduct_inventory``)."""
    restore: dict[int, int] = {}
    for item in items:
        pid = item.get("product_id")
        if pid:
            restore[pid] = restore.get(pid, 0) + int(item.get("quantity") or 0)
    for product_id, qty in restore.items():
        await db.execute(
            update(Products)
            .where(Products.id == product_id, Products.client_id == client_id)
            .values(quantity=Products.quantity + qty)
        )


@router.post(
    "/transactions/{txn_id}/refund",
    response_model=RefundResponse,
    dependencies=[Depends(require_permission("pos.refund"))],
)
async def refund_transaction(
    txn_id: int,
    background_tasks: BackgroundTasks,
    payload: Optional[RefundRequest] = None,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Refund a sale by issuing a ZATCA **credit note** (POS-07).

    Supports **full, partial, and line-level** refunds. Omit ``lines`` (or POST an
    empty body) to refund the whole remaining balance; pass
    ``lines:[{product_id, quantity}]`` to return only selected units. Quantities
    are validated against what is still un-refunded across any earlier partial
    refunds, so an invoice can never be over-refunded.

    Creates a type-381 credit note that references the original invoice, restores
    only the returned units to stock (branch-aware), advances the hash chain, is
    ECDSA-signed and queued for Fatoora reporting — all atomically. The credit-note
    transaction stores negative amounts (prorated to the returned lines) so sales
    reports net out; the signed ZATCA document carries the compliant positive
    credit-note amounts. The original lands in ``refunded`` when everything is
    returned, else ``partial_refunded`` while a balance remains.
    """
    client = await get_client_for_user(db, str(current_user.id))
    original = await _get_owned_transaction(db, client, txn_id)

    if (original.total_amount or 0) < 0 or (original.payment_method or "") == "refund":
        raise HTTPException(status_code=400, detail="Cannot refund a credit note")
    if (original.status or "") == "refunded":
        raise HTTPException(status_code=400, detail="Transaction already refunded")
    if (original.status or "") == "voided":
        raise HTTPException(status_code=400, detail="Cannot refund a voided sale")

    try:
        items = json.loads(original.items_json) if original.items_json else []
    except (ValueError, TypeError):
        items = []

    # Aggregate the original lines by product so duplicate lines and per-line
    # discounts collapse to one authoritative entry per SKU.
    orig_by_pid: dict[int, dict] = {}
    for it in items:
        pid = it.get("product_id")
        if pid is None:
            continue
        pid = int(pid)
        entry = orig_by_pid.setdefault(
            pid,
            {"product_id": pid, "name": it.get("name") or "Item",
             "price": float(it.get("price") or 0), "quantity": 0.0, "discount": 0.0},
        )
        entry["quantity"] += float(it.get("quantity") or 0)
        entry["discount"] += float(it.get("discount") or 0)

    already = await _refunded_quantities(db, original.id)

    # Resolve the requested quantities: explicit lines, else the whole remaining
    # balance (legacy whole-invoice refund).
    requested: dict[int, float] = {}
    if payload and payload.lines:
        for ln in payload.lines:
            q = float(ln.quantity or 0)
            if q <= 0:
                continue
            requested[int(ln.product_id)] = requested.get(int(ln.product_id), 0.0) + q
        if not requested:
            raise HTTPException(status_code=400, detail="No refund quantities specified")
    else:
        for pid, e in orig_by_pid.items():
            remaining = e["quantity"] - already.get(pid, 0.0)
            if remaining > 1e-9:
                requested[pid] = remaining
        if not requested:
            raise HTTPException(status_code=400, detail="Transaction already refunded")

    # Validate every requested line against what is still refundable.
    for pid, q in requested.items():
        if pid not in orig_by_pid:
            raise HTTPException(
                status_code=400, detail=f"Product {pid} is not on the original invoice"
            )
        remaining = orig_by_pid[pid]["quantity"] - already.get(pid, 0.0)
        if q > remaining + 1e-9:
            raise HTTPException(
                status_code=400,
                detail=f"Refund quantity {q} exceeds remaining {remaining} for product {pid}",
            )

    # Build the returned-line list (drives stock restore, the credit-note
    # items_json, and the proportional amounts), prorating per-line discounts.
    refund_items: List[dict] = []
    for pid, q in requested.items():
        e = orig_by_pid[pid]
        frac = (q / e["quantity"]) if e["quantity"] else 0.0
        refund_items.append({
            "product_id": pid,
            "name": e["name"],
            "price": e["price"],
            "quantity": q,
            "discount": round(e["discount"] * frac, 4),
        })

    # Prorate the order-level discount/VAT/total by the share of the line subtotal
    # being returned. A full refund (ratio == 1.0) reproduces the original amounts
    # exactly; partial refunds net only their share.
    orig_line_subtotal = sum(
        e["price"] * e["quantity"] - e["discount"] for e in orig_by_pid.values()
    )
    refund_line_subtotal = sum(it["price"] * it["quantity"] - it["discount"] for it in refund_items)
    ratio = (refund_line_subtotal / orig_line_subtotal) if orig_line_subtotal else 0.0
    refund_subtotal = round(refund_line_subtotal, 2)
    refund_discount = round((original.discount_amount or 0) * ratio, 2)
    refund_vat = round((original.vat_amount or 0) * ratio, 2)
    refund_total = round((original.total_amount or 0) * ratio, 2)

    # Restore only the returned units to the same stock pool the sale deducted
    # from (branch ledger when the original was branch-tagged, else client-level).
    if original.branch_id:
        from services.branch_stock import restore_branch_inventory

        await restore_branch_inventory(
            db, str(current_user.id), client.id, int(original.branch_id), refund_items
        )
    else:
        await _restore_inventory(db, client.id, refund_items)

    # Allocate the credit note its own sequential invoice number.
    current_counter = (client.invoice_counter or 0) + 1
    await db.execute(
        update(Clients).where(Clients.id == client.id).values(invoice_counter=current_counter)
    )
    credit_number = f"CRN-{client.id:04d}-{current_counter:06d}"

    credit = Transactions(
        user_id=str(current_user.id),
        client_id=client.id,
        invoice_number=credit_number,
        subtotal=-refund_subtotal,
        vat_amount=-refund_vat,
        discount_amount=-refund_discount,
        total_amount=-refund_total,
        payment_method="refund",
        status="credit_note",
        items_json=json.dumps(refund_items, ensure_ascii=False),
        original_transaction_id=original.id,
        customer_name=original.customer_name,
        customer_phone=original.customer_phone,
        customer_vat_number=original.customer_vat_number,
    )
    db.add(credit)

    # Decide the original's new state: fully refunded once every line's
    # cumulative refunded quantity reaches its sold quantity, else partial.
    fully_refunded = all(
        (already.get(pid, 0.0) + requested.get(pid, 0.0)) >= e["quantity"] - 1e-9
        for pid, e in orig_by_pid.items()
    )
    original.status = "refunded" if fully_refunded else "partial_refunded"

    # Net the refund into the open shift (negative amount) so cash reconciles.
    credit.shift_id = await _apply_sale_to_open_shift(
        db, str(current_user.id), credit.total_amount
    )

    await db.flush()

    # PAY-10 / F-004: route the refund back to the original tender(s). Each
    # card-like leg is reversed through the capturing gateway; every reversed leg
    # is recorded as a `refunded` tender on the credit note so the money movement
    # is auditable and the drawer reconciliation can tell the cash portion of a
    # refund from the card portion. A gateway failure rolls the credit note back.
    refund_tender_rows = await _refund_tenders(db, original, refund_total)
    _persist_tenders(db, str(current_user.id), client.id, credit.id, refund_tender_rows)

    doc, stamped_qr = await zatca_sale.sign_transaction(
        db,
        client,
        credit,
        document_type="credit_note",
        invoice_type_code="381",
        billing_reference=original.invoice_number,
        # ZA-06: a B2B credit note inherits the original sale's buyer VAT so it is
        # cleared/reported on the same path as the invoice it reverses.
        buyer_vat=credit.customer_vat_number,
    )
    document_id = doc.id

    await db.commit()
    await db.refresh(credit)

    background_tasks.add_task(zatca_sale.report_document_background, document_id, client.id)
    background_tasks.add_task(
        fire_event_background,
        str(current_user.id),
        "refund.created",
        {
            "credit_note_id": credit.id,
            "credit_note_number": credit_number,
            "original_transaction_id": original.id,
            "total_amount": credit.total_amount,
            "client_id": client.id,
        },
    )

    return RefundResponse(
        credit_note_id=credit.id,
        original_transaction_id=original.id,
        credit_note_number=credit_number,
        total_amount=credit.total_amount,
        zatca_qr=stamped_qr,
        zatca_qr_base64=zatca_service_mod.render_qr_png_base64(stamped_qr),
        zatca_document_id=document_id,
        zatca_status="signed",
        original_status=original.status,
    )


# ---------- Invoice document & receipt delivery ----------
class EmailReceiptRequest(BaseModel):
    to_email: str


class SmsReceiptRequest(BaseModel):
    to_number: str


# ---------- Void a sale (audited, permissioned) — POS-08 ----------
class VoidRequest(BaseModel):
    """Optional reason for the audit trail when voiding a sale."""

    reason: Optional[str] = None


class VoidResponse(BaseModel):
    transaction_id: int
    invoice_number: str
    status: str


@router.post(
    "/transactions/{txn_id}/void",
    response_model=VoidResponse,
    dependencies=[Depends(require_permission("pos.void"))],
)
async def void_transaction(
    txn_id: int,
    payload: Optional[VoidRequest] = None,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Void a sale (POS-08) — an **audited** cancellation gated by ``pos.void``.

    A void cancels a whole sale that was rung in error: the sale is marked
    ``voided``, every deducted unit is restored to the same stock pool the sale
    drew from (the branch ledger when branch-tagged, else client-level), and an
    ``audit_logs`` row records who voided what and why (fraud control / SEC-07).
    A voided sale is excluded from sales/Z-report revenue and from the drawer
    reconciliation (it never happened — see ``features.py`` / F-008/F-009 which
    already skip the ``voided`` status), so the shift counters need no rewrite.

    Distinct from a **refund**, which issues a ZATCA **credit note** (F-007).
    For ZATCA compliance a void is therefore only allowed while the sale's
    fiscal document has **not** yet been accepted by the authority — once the
    invoice is ``cleared``/``reported`` the compliant reversal is a credit note,
    so this returns 409 and the cashier must refund instead.

    Owner-scoped (SEC-02): ``_get_owned_transaction`` filters on the caller's
    client, so one client can never void another client's sale (foreign id →
    404).
    """
    client = await get_client_for_user(db, str(current_user.id))
    txn = await _get_owned_transaction(db, client, txn_id)

    status_now = txn.status or "completed"
    if (txn.total_amount or 0) < 0 or (txn.payment_method or "") == "refund" or status_now == "credit_note":
        raise HTTPException(status_code=400, detail="Cannot void a credit note")
    if status_now == "voided":
        raise HTTPException(status_code=400, detail="Transaction already voided")
    if status_now in ("refunded", "partial_refunded"):
        raise HTTPException(
            status_code=400,
            detail="A refunded sale cannot be voided — it already has a credit note",
        )
    if status_now == "held":
        raise HTTPException(
            status_code=400, detail="A held ticket is not a sale; discard it instead of voiding"
        )

    # ZATCA compliance: a fiscally-accepted invoice (cleared/reported) must be
    # reversed by a credit note, not voided.
    accepted = (
        await db.execute(
            select(ZatcaDocuments.id).where(
                ZatcaDocuments.transaction_id == txn.id,
                ZatcaDocuments.status.in_(("cleared", "reported")),
            )
        )
    ).first()
    if accepted:
        raise HTTPException(
            status_code=409,
            detail=(
                "This invoice has been reported to ZATCA; issue a credit-note "
                "refund instead of voiding it."
            ),
        )

    # Restore stock to the same pool the sale deducted from (branch-aware).
    try:
        items = json.loads(txn.items_json) if txn.items_json else []
    except (ValueError, TypeError):
        items = []
    if txn.branch_id:
        from services.branch_stock import restore_branch_inventory

        await restore_branch_inventory(
            db, str(current_user.id), client.id, int(txn.branch_id), items
        )
    else:
        await _restore_inventory(db, client.id, items)

    txn.status = "voided"

    # Audit trail (SEC-07 / POS-08): who voided which sale, and why.
    reason = (payload.reason or "").strip() if payload else ""
    db.add(
        Audit_logs(
            user_id=str(current_user.id),
            action="POS_VOID_SALE",
            entity_type="transactions",
            entity_id=str(txn.id),
            details=(
                f"Voided sale {txn.invoice_number} (total {txn.total_amount})"
                + (f" — reason: {reason}" if reason else "")
            ),
        )
    )

    await db.commit()
    await db.refresh(txn)

    return VoidResponse(
        transaction_id=txn.id,
        invoice_number=txn.invoice_number,
        status=txn.status,
    )


async def _get_owned_transaction(db: AsyncSession, client: Clients, txn_id: int) -> Transactions:
    result = await db.execute(
        select(Transactions).where(
            Transactions.id == txn_id, Transactions.client_id == client.id
        )
    )
    txn = result.scalar_one_or_none()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return txn


@router.get("/transactions/{txn_id}/invoice", response_class=HTMLResponse)
async def get_invoice_document(
    txn_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Render the ZATCA tax invoice as an **always-Arabic** print-ready document.

    The receipts/quotations-always-Arabic rule (SRS §7) is enforced here: the
    document is rendered RTL/Arabic regardless of the caller's UI language. The
    returned HTML is print-to-PDF ready in any browser; wire a headless renderer
    (e.g. WeasyPrint) in front of this for server-side PDF bytes.
    """
    client = await get_client_for_user(db, str(current_user.id))
    txn = await _get_owned_transaction(db, client, txn_id)

    try:
        line_items = json.loads(txn.items_json) if txn.items_json else []
    except (ValueError, TypeError):
        line_items = []

    issue_date = txn.created_at.strftime("%Y-%m-%d %H:%M") if txn.created_at else ""
    html = PDFInvoiceService.generate_invoice_html(
        seller_name=client.business_name or "Business",
        seller_vat=client.vat_number or "000000000000000",
        buyer_name=txn.customer_name or "نقدي",  # "Cash" customer in Arabic
        buyer_vat=txn.customer_vat_number or "",
        invoice_number=txn.invoice_number,
        issue_date=issue_date,
        line_items=line_items,
        subtotal=txn.subtotal or 0,
        vat_amount=txn.vat_amount or 0,
        total_amount=txn.total_amount,
        zatca_qr=txn.zatca_qr or "",
        discount=txn.discount_amount or 0,
    )
    return HTMLResponse(content=html)


@router.get("/transactions/{txn_id}/pdf")
async def get_invoice_pdf(
    txn_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the tax invoice as real ``application/pdf`` bytes (Phase 6 PDF).

    Rendered server-side with the fiscal ZATCA QR embedded. The frontend offers
    this as a "Download PDF" action on receipts/invoices.
    """
    from fastapi.responses import Response

    from services.pdf_render import invoice_pdf_bytes

    client = await get_client_for_user(db, str(current_user.id))
    txn = await _get_owned_transaction(db, client, txn_id)

    try:
        line_items = json.loads(txn.items_json) if txn.items_json else []
    except (ValueError, TypeError):
        line_items = []

    issue_date = txn.created_at.strftime("%Y-%m-%d %H:%M") if txn.created_at else ""
    qr_png = (
        zatca_service_mod.render_qr_png_base64(txn.zatca_qr) if txn.zatca_qr else None
    )
    try:
        pdf_bytes = invoice_pdf_bytes(
            seller_name=client.business_name or "Business",
            seller_vat=client.vat_number or "000000000000000",
            buyer_name=txn.customer_name or "Cash",
            buyer_vat=txn.customer_vat_number or "",
            invoice_number=txn.invoice_number,
            issue_date=issue_date,
            line_items=line_items,
            subtotal=txn.subtotal or 0,
            discount=txn.discount_amount or 0,
            vat_amount=txn.vat_amount or 0,
            total_amount=txn.total_amount,
            qr_png_base64=qr_png,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=501, detail=str(exc))

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{txn.invoice_number}.pdf"'
        },
    )


@router.get("/transactions/{txn_id}/escpos")
async def get_escpos_receipt(
    txn_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return a base64 ESC/POS byte stream for thermal printing (Phase E).

    The frontend streams the decoded bytes to a WebUSB / Web Bluetooth thermal
    printer. The embedded QR is the canonical ZATCA TLV payload, so the printed
    receipt carries the same fiscal QR as the always-Arabic HTML invoice.
    """
    client = await get_client_for_user(db, str(current_user.id))
    txn = await _get_owned_transaction(db, client, txn_id)

    try:
        line_items = json.loads(txn.items_json) if txn.items_json else []
    except (ValueError, TypeError):
        line_items = []

    issue_date = txn.created_at.strftime("%Y-%m-%d %H:%M") if txn.created_at else ""

    # HW-04: kick the cash drawer when the sale took any cash. Prefer the captured
    # tenders (handles a split with a cash leg); fall back to the method label for
    # legacy tender-less sales.
    cash_legs = (
        await db.execute(
            select(func.count(PaymentTenders.id)).where(
                PaymentTenders.transaction_id == txn.id,
                PaymentTenders.tender_type == "cash",
                PaymentTenders.status == "captured",
            )
        )
    ).scalar() or 0
    open_drawer = cash_legs > 0 or normalize_tender_type(txn.payment_method) == "cash"

    payload = build_receipt_base64(
        seller_name=client.business_name or "Store",
        vat_number=client.vat_number or "",
        invoice_number=txn.invoice_number,
        issue_date=issue_date,
        line_items=line_items,
        subtotal=txn.subtotal or 0,
        discount=txn.discount_amount or 0,
        vat_amount=txn.vat_amount or 0,
        total_amount=txn.total_amount,
        zatca_qr=txn.zatca_qr or "",
        open_drawer=open_drawer,
    )
    return {
        "invoice_number": txn.invoice_number,
        "format": "escpos",
        "encoding": "base64",
        "data": payload,
    }


@router.post(
    "/transactions/{txn_id}/email",
    dependencies=[Depends(require_feature("email_receipts"))],
)
async def email_invoice_receipt(
    txn_id: int,
    data: EmailReceiptRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Email a receipt for a transaction (POS-04).

    Gated by the per-client ``email_receipts`` feature flag (AG-03): an agent can
    disable receipt emailing for a specific client. Uses the EmailService
    (stub-logs until SMTP is configured).
    """
    client = await get_client_for_user(db, str(current_user.id))
    txn = await _get_owned_transaction(db, client, txn_id)

    to_email = (data.to_email or "").strip()
    if not to_email:
        raise HTTPException(status_code=400, detail="to_email is required")

    return await EmailService.send_transaction_receipt(
        to_email=to_email,
        invoice_number=txn.invoice_number,
        total=txn.total_amount,
    )


@router.post(
    "/transactions/{txn_id}/sms",
    dependencies=[Depends(require_feature("sms_receipts"))],
)
async def sms_invoice_receipt(
    txn_id: int,
    data: SmsReceiptRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a transaction receipt by SMS (POS-04).

    Gated by the per-client ``sms_receipts`` feature flag (AG-03). Uses the Twilio
    transport (``core.sms``) when configured and otherwise logs in dev mode; the
    ``delivered`` flag tells the caller which path ran.
    """
    from core.sms import send_sms

    client = await get_client_for_user(db, str(current_user.id))
    txn = await _get_owned_transaction(db, client, txn_id)

    to_number = (data.to_number or "").strip()
    if not to_number:
        raise HTTPException(status_code=400, detail="to_number is required")

    body = f"إيصال {txn.invoice_number}: الإجمالي {txn.total_amount:.2f} ر.س"
    delivered = await send_sms(to_number, body)
    return {
        "status": "sent" if delivered else "logged",
        "to": to_number,
        "invoice_number": txn.invoice_number,
        "delivered": delivered,
    }


# ---------- Per-branch stock ledger (Phase 6 multi-branch) ----------
class BranchStockSetRequest(BaseModel):
    product_id: int
    quantity: int


@router.get("/branches/{branch_id}/stock")
async def get_branch_stock(
    branch_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List the per-branch stock ledger for a branch (branch-scoped stock report)."""
    from services.branch_stock import list_branch_stock

    client = await get_client_for_user(db, str(current_user.id))
    rows = await list_branch_stock(db, client.id, branch_id)
    return {
        "branch_id": branch_id,
        "items": [
            {"product_id": r.product_id, "quantity": r.quantity} for r in rows
        ],
        "total": len(rows),
    }


@router.put("/branches/{branch_id}/stock")
async def set_branch_stock_endpoint(
    branch_id: int,
    data: BranchStockSetRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Allocate/adjust a product's stock for a specific branch."""
    from services.branch_stock import set_branch_stock

    client = await get_client_for_user(db, str(current_user.id))
    row = await set_branch_stock(
        db, str(current_user.id), client.id, branch_id, data.product_id, data.quantity
    )
    return {
        "branch_id": branch_id,
        "product_id": row.product_id,
        "quantity": row.quantity,
    }