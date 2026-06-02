import base64
import hashlib
import json
import logging
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
from dependencies.permissions import require_permission
from schemas.auth import UserResponse
from models.clients import Clients
from models.products import Products
from models.transactions import Transactions
from services import loyalty as loyalty_service
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
    price: float
    quantity: int
    discount: Optional[float] = 0


class PaymentEntry(BaseModel):
    """One tender line of a (possibly split) payment, e.g. cash + card."""

    method: str  # "cash", "card", "transfer", "loyalty"
    amount: float


class CreateTransactionRequest(BaseModel):
    items: List[CartItem]
    payment_method: str  # "cash", "card", "mixed"
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
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

    discount_amount = data.discount_amount or 0

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
        branch_id=data.branch_id,
    )
    db.add(transaction)

    # ---- Atomic inventory deduction (same transaction as the sale) ----
    # The sale, the invoice-counter increment, and every stock decrement are
    # committed together. If stock is insufficient (and overselling isn't
    # allowed) we raise before commit, so nothing is persisted and the counter
    # is not consumed — fixing the previous fire-and-forget deduction gap.
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
    doc, stamped_qr = await zatca_sale.sign_transaction(db, client, transaction)
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
    )
    db.add(transaction)

    await _deduct_inventory(db, client.id, items, bool(txn.get("allow_negative_stock")))
    transaction.shift_id = await _apply_sale_to_open_shift(db, user_id, total_amount)

    await db.flush()
    doc, _stamped_qr = await zatca_sale.sign_transaction(db, client, transaction)
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

    filters = [Transactions.client_id == client.id]
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


# ---------- Refund / ZATCA credit note (POS-07) ----------
class RefundResponse(BaseModel):
    credit_note_id: int
    original_transaction_id: int
    credit_note_number: str
    total_amount: float
    zatca_qr: Optional[str] = None
    zatca_qr_base64: Optional[str] = None
    zatca_document_id: int
    zatca_status: str


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
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Refund a sale by issuing a ZATCA **credit note** (POS-07).

    Replaces the previous negative-price fake refund. Creates a type-381 credit
    note that references the original invoice, restores inventory, advances the
    hash chain, is ECDSA-signed and queued for Fatoora reporting — all atomically.
    The credit-note transaction stores negative amounts so sales reports net out;
    the signed ZATCA document carries the compliant positive credit-note amounts.
    """
    client = await get_client_for_user(db, str(current_user.id))
    original = await _get_owned_transaction(db, client, txn_id)

    if (original.total_amount or 0) < 0 or (original.payment_method or "") == "refund":
        raise HTTPException(status_code=400, detail="Cannot refund a credit note")
    if (original.status or "") == "refunded":
        raise HTTPException(status_code=400, detail="Transaction already refunded")

    try:
        items = json.loads(original.items_json) if original.items_json else []
    except (ValueError, TypeError):
        items = []

    await _restore_inventory(db, client.id, items)

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
        subtotal=-(original.subtotal or 0),
        vat_amount=-(original.vat_amount or 0),
        discount_amount=-(original.discount_amount or 0),
        total_amount=-(original.total_amount or 0),
        payment_method="refund",
        status="credit_note",
        items_json=original.items_json,
        customer_name=original.customer_name,
        customer_phone=original.customer_phone,
    )
    db.add(credit)
    original.status = "refunded"

    # Net the refund into the open shift (negative amount) so cash reconciles.
    credit.shift_id = await _apply_sale_to_open_shift(
        db, str(current_user.id), credit.total_amount
    )

    await db.flush()
    doc, stamped_qr = await zatca_sale.sign_transaction(
        db,
        client,
        credit,
        document_type="credit_note",
        invoice_type_code="381",
        billing_reference=original.invoice_number,
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
    )


# ---------- Invoice document & receipt delivery ----------
class EmailReceiptRequest(BaseModel):
    to_email: str


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