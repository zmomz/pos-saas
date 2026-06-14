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
from dependencies.tenancy import get_owner_id
from dependencies.features import require_feature
from dependencies.permissions import has_permission, require_permission
from schemas.auth import UserResponse
from models.audit_logs import Audit_logs
from models.clients import Clients
from models.customers import Customers
from models.products import Products
from models.transactions import Transactions
from models.payment_tenders import PaymentTenders
from models.zatca_documents import ZatcaDocuments
# Imported so the per-branch stock table registers on Base.metadata at startup
# (services.branch_stock is only imported lazily inside handlers).
from models.product_branch_stock import Product_branch_stock  # noqa: F401
# Imported so the variant table registers on Base.metadata at startup
# (services.product_variants is only imported lazily inside handlers).
from models.product_variants import Product_variants  # noqa: F401
from models.variant_branch_stock import Variant_branch_stock  # noqa: F401
from services import loyalty as loyalty_service
from services.discounts import (
    DiscountsService,
    DiscountValidationError,
    compute_discount_amount,
)
from services.payment_gateway import (
    GatewayNotConfigured,
    PaymentDeclined,
    get_gateway_for,
    normalize_tender_type,
    requires_capture,
)
from services import zatca as zatca_service_mod
from services import zatca_sale
from services.sale_core import (
    NormalizedCart,
    execute_sale,
    # The atomic-sale helpers now live in the sale core; re-imported under their
    # historical private names so the offline-sync and refund paths are unchanged.
    apply_sale_to_open_shift as _apply_sale_to_open_shift,
    attach_terminal_gateways as _attach_terminal_gateways,
    capture_tenders as _capture_tenders,
    deduct_inventory as _deduct_inventory,
    persist_tenders as _persist_tenders,
    redeem_gift_cards as _redeem_gift_cards,
)
from services.escpos import build_receipt_base64
from services.printers import resolve_printer
from services.receipt_templates import load_default_template
from services.store_settings import get_store_settings
from services.production import EmailService, LowStockChecker, PDFInvoiceService, fire_event_background
from services.promotions import price_cart_promotions
from services.system_settings import get_effective_tax_rate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/pos", tags=["pos"])


# ---------- Pydantic Schemas ----------
class CartItem(BaseModel):
    # Optional because a *combo* line (ISSUE-066) carries ``combo_id`` and no single
    # product_id — it is expanded into its component product lines before the sale
    # so each component's stock is deducted (ISSUE-032 parity). A normal catalog
    # line always carries product_id.
    product_id: Optional[int] = None
    name: str
    # Arabic product name carried into items_json so the always-Arabic thermal
    # receipt prints the Arabic line name (PRN-01 / L10N-06, F-021). Optional —
    # falls back to ``name`` when absent.
    name_ar: Optional[str] = None
    # POS-11 (F-011): when the product is open-price this is the sale-time unit
    # price the cashier entered; for a fixed-price product it is the catalog price.
    price: float
    # POS-11 (F-011): a Float so a weighted product can be sold by fractional weight
    # (e.g. 0.45 kg). Unit-count products still pass whole numbers.
    quantity: float
    discount: Optional[float] = 0
    # INV-04 (F-033): when the line is a product *variant* (size/colour SKU), this
    # is the variant's id. The sale then decrements *that variant's* stock
    # independently of sibling variants, instead of the parent product's quantity.
    variant_id: Optional[int] = None
    # ISSUE-066: a retail combo line. The bundle is rung up at ``price`` × ``quantity``
    # but deducts no stock on its own; before the sale it is expanded into one line
    # per component product (component-qty × line-qty) so the component stock is
    # depleted exactly like the restaurant settle path (ISSUE-032).
    combo_id: Optional[int] = None


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
    # Gift card / store credit (CRM-03/PRC-05, F-038). When this leg's tender is a
    # gift card, the bearer code the cashier scanned/entered; the card's balance is
    # validated and atomically decremented inside the sale (no gateway round-trip).
    gift_card_code: Optional[str] = None


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
    # Gratuity collected on top of the invoice total (POS-13 tips, F-012). It is
    # OUTSIDE the VAT base (not part of the taxable supply) so it never changes the
    # subtotal/VAT/total the ZATCA document is stamped on; it is added to the amount
    # the tenders must cover and reported per shift in the Z-report. A split's
    # per-tender amounts therefore sum to total_amount + tip_amount.
    tip_amount: Optional[float] = 0
    # Cash-drawer change helper (ISSUE-074). The cash the customer handed over for
    # the cash portion of the sale; the server computes + records the change owed
    # back (change_due). Must cover the cash amount due. Drawer-facing only — it
    # never changes the invoice total or the captured tender. Null on a card sale.
    cash_tendered: Optional[float] = None
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
    # Gift card / store credit (CRM-03/PRC-05, F-038) for a single-tender giftcard
    # sale (when ``payments`` is not given and ``payment_method`` is "giftcard"): the
    # bearer code whose balance is validated and atomically decremented in the sale.
    payment_gift_card_code: Optional[str] = None


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


class AppliedPromotionInfo(BaseModel):
    """One auto-applied promotion that fired on the sale (ISSUE-058)."""

    promotion_id: Optional[int] = None
    name: str
    kind: str
    amount: float


class TransactionResponse(BaseModel):
    id: int
    invoice_number: str
    subtotal: float
    vat_amount: float
    discount_amount: float
    total_amount: float
    # Gratuity collected on top of total_amount (POS-13, F-012); null when no tip.
    # The customer paid total_amount + tip_amount across the tenders.
    tip_amount: Optional[float] = None
    # Cash-drawer change helper (ISSUE-074); null on a non-cash / unentered sale.
    # cash_tendered is what the customer handed over, change_due what they get back.
    cash_tendered: Optional[float] = None
    change_due: Optional[float] = None
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
    # Auto-applied promotions (ISSUE-058): the line/category/BOGO promos this cart
    # earned, so the cashier sees why the order discount fired. Folded into
    # ``discount_amount``; null when nothing fired.
    applied_promotions: Optional[List[AppliedPromotionInfo]] = None
    # Captured tenders (PAY-01): the network/approval proof for each card-like
    # tender, so the receipt can show how the sale was really paid.
    tenders: Optional[List[TenderInfo]] = None


class TransactionListResponse(BaseModel):
    items: List[TransactionResponse]
    total: int
    page: int
    page_size: int


# ---------- ZATCA QR Helper ----------
# The legacy in-router ``generate_zatca_tlv`` / ``generate_zatca_hash`` helpers
# were removed (ISSUE-016): the real, stamped 8-tag QR TLV and the C14N invoice
# hash are produced by the canonical signer ``services.zatca_sale.sign_transaction``
# on the atomic sale path. There is one signing/QR implementation, not two.


# ---------- Helper: Saudi-real tender capture (PAY-01/05) ----------
# The atomic-sale helpers (_deduct_inventory, _apply_sale_to_open_shift,
# _capture_tenders, _redeem_gift_cards, _attach_terminal_gateways, _persist_tenders)
# now live in ``services.sale_core`` and are imported above under these names so the
# offline-sync and refund paths below are unchanged. Only the request-shaped
# ``_build_tender_specs`` (it reads a CreateTransactionRequest) stays here.
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
                "gift_card_code": p.gift_card_code,
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
            "gift_card_code": data.payment_gift_card_code,
        }
    ]


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


# ---------- Barcode resolution (INV-04 / POS-06): scan → product or variant ----------
class BarcodeResolution(BaseModel):
    """The product/variant a scanned barcode resolves to (INV-04, F-033)."""

    kind: str  # "variant" | "product" | "none"
    product_id: Optional[int] = None
    variant_id: Optional[int] = None
    name: str = ""
    name_ar: Optional[str] = None
    price: float = 0.0
    barcode: Optional[str] = None
    quantity: Optional[int] = None
    sku: Optional[str] = None


@router.get("/resolve-barcode", response_model=BarcodeResolution)
async def resolve_barcode(
    barcode: str = Query(..., description="The scanned barcode/SKU"),
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Resolve a scanned barcode to one of the caller's variants or products.

    A **variant** barcode wins over a product barcode (it is the more specific
    sellable SKU, INV-04), and the resolution returns the variant's own price and
    stock plus the parent product's id/Arabic name so the POS adds it as a variant
    line. Owner-scoped (SEC-02): only the caller's own catalog is searched.
    """
    from services.product_variants import resolve_variant_barcode, resolve_product_barcode

    variant = await resolve_variant_barcode(db, owner_id, barcode)
    if variant:
        parent = (
            await db.execute(
                select(Products).where(
                    Products.id == variant.product_id,
                    Products.user_id == owner_id,
                )
            )
        ).scalar_one_or_none()
        return BarcodeResolution(
            kind="variant",
            product_id=variant.product_id,
            variant_id=variant.id,
            name=variant.name,
            name_ar=(parent.name_ar if parent else None),
            price=float(variant.price if variant.price is not None else (parent.price if parent else 0)),
            barcode=variant.barcode,
            quantity=variant.quantity,
            sku=variant.sku,
        )

    product = await resolve_product_barcode(db, owner_id, barcode)
    if product:
        return BarcodeResolution(
            kind="product",
            product_id=product.id,
            name=product.name,
            name_ar=product.name_ar,
            price=float(product.price or 0),
            barcode=product.barcode,
            quantity=product.quantity,
        )
    return BarcodeResolution(kind="none")


async def expand_combo_lines(
    db: AsyncSession, user_id: str, items: List["CartItem"]
) -> List["CartItem"]:
    """Replace each combo line with its component product lines (ISSUE-066/032).

    A combo line (``combo_id`` set, ``product_id`` ``None``) prices the bundle but
    deducts no stock on its own — a silent oversell. Here it is expanded into one
    line per component product (qty = component-qty × line-qty), its ``line_total``
    allocated across the components in proportion to catalog price, so the expanded
    lines re-sum to the same goods subtotal AND the sale core then deducts each
    component's stock. Non-combo lines pass through unchanged; a combo that is
    deleted / has no valid components keeps its original (non-deducting) line so the
    charge is preserved rather than silently dropped. Reuses ``RestaurantService``
    so retail and the restaurant settle path expand combos identically.
    """
    if not any(getattr(it, "combo_id", None) for it in items):
        return list(items)

    from services.restaurant import RestaurantService

    service = RestaurantService(db)
    out: List["CartItem"] = []
    for it in items:
        combo_id = getattr(it, "combo_id", None)
        if combo_id is None:
            out.append(it)
            continue
        combo = await service.get_combo(int(combo_id), user_id)
        components = (
            service._normalize_components(service._load_components(combo)) if combo else []
        )
        if not components:
            out.append(it)
            continue
        line_qty = float(it.quantity or 0)
        line_total = round(float(it.price or 0) * line_qty - float(it.discount or 0), 2)
        metas: List[tuple] = []
        weights: List[float] = []
        for comp in components:
            pid = comp["product_id"]
            comp_qty = float(comp.get("qty") or 1)
            product = await service._owned_product(pid, user_id)
            price = float(product.price) if product is not None else 0.0
            name = product.name if product is not None else f"product:{pid}"
            metas.append((pid, comp_qty, name))
            weights.append(price * comp_qty)
        allocations = service._allocate(line_total, weights)
        for (pid, comp_qty, name), alloc in zip(metas, allocations):
            q = round(comp_qty * line_qty, 4)
            unit = round(alloc / q, 4) if q else 0.0
            out.append(CartItem(product_id=pid, name=name, price=unit, quantity=q))
    return out


# ---------- Endpoints ----------
@router.post("/transaction", response_model=TransactionResponse)
async def create_transaction(
    data: CreateTransactionRequest,
    background_tasks: BackgroundTasks,
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Create a new POS transaction, ECDSA-signed and ZATCA-reported (C-3/C-4)."""
    client = await get_client_for_user(db, owner_id)

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
    # Variant lines (INV-04) carry their own price by design, so they are not a
    # price *override* of the parent product — exclude them from this gate.
    # Open-price products (POS-11/F-011) expect a sale-time price by design, so a
    # price entered on them is NOT a fraud-sensitive override — exclude them too.
    override_pids = [it.product_id for it in data.items if it.product_id and not it.variant_id]
    if override_pids:
        catalog = {
            row.id: (float(row.price or 0), bool(row.is_open_price))
            for row in (
                await db.execute(
                    select(Products.id, Products.price, Products.is_open_price).where(
                        Products.id.in_(override_pids),
                        Products.client_id == client.id,
                    )
                )
            ).all()
        }
        has_override = any(
            not it.variant_id
            and it.product_id in catalog
            and not catalog[it.product_id][1]  # open-price: sale-time price is expected
            and abs(float(it.price) - catalog[it.product_id][0]) > 0.001
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
                discount_code, subtotal, user_id=owner_id
            )
        except DiscountValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        discount_amount = compute_discount_amount(discount_rule, subtotal)
        if not await discounts_service.consume(
            discount_rule.id, user_id=owner_id
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
    program = await loyalty_service.get_active_program(db, owner_id)
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
                user_id=owner_id,
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

    # ---- Auto-applied promotions (ISSUE-058, P2 pricing) ----
    # Line/category/BOGO promotions the merchant configured fire on their own when
    # the cart meets their conditions, on top of any coded/manual/loyalty discount.
    # The promotion discount folds into ``discount_amount`` so it reduces the taxable
    # base exactly like the order discount — composing with VAT. ``applied_promotions``
    # surfaces on the response so the cashier sees which promos the cart earned.
    promo_result = await price_cart_promotions(db, owner_id, client.id, data.items)
    applied_promotions = promo_result.applied
    if promo_result.total_discount > 0:
        discount_amount = round(discount_amount + promo_result.total_discount, 2)
    # Never let stacked discounts push the taxable base below zero.
    discount_amount = round(min(discount_amount, subtotal), 2)

    taxable_amount = subtotal - discount_amount
    # MA-05: the master's global VAT rate is authoritative; the request rate is
    # only a fallback for installs with no global rate configured.
    vat_rate = await get_effective_tax_rate(db, data.vat_rate)
    vat_amount = round(taxable_amount * (vat_rate / 100), 2)
    total_amount = round(taxable_amount + vat_amount, 2)

    # ---- Tip / gratuity (POS-13, F-012) ----
    # A tip is collected on TOP of the invoice total and is OUTSIDE the VAT base —
    # it has already been excluded above (VAT is on taxable_amount only), so the
    # ZATCA document's subtotal/VAT/total are unaffected. ``charge_total`` is what
    # the customer actually pays (and what the tenders must cover); the tip is
    # recorded separately and surfaced in the Z-report and on the receipt.
    tip_amount = round(float(data.tip_amount or 0), 2)
    if tip_amount < 0:
        raise HTTPException(status_code=400, detail="tip_amount cannot be negative")
    charge_total = round(total_amount + tip_amount, 2)

    # ---- Payment breakdown (POS-02): validate + summarise split tenders ----
    payment_breakdown_json: Optional[str] = None
    payment_method = data.payment_method
    if data.payments:
        paid_total = round(sum(p.amount for p in data.payments), 2)
        if abs(paid_total - charge_total) > 0.01:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Payment breakdown total {paid_total:.2f} does not match "
                    f"amount due {charge_total:.2f}"
                ),
            )
        # Redact the gift-card bearer code from the stored breakdown (it is the
        # secret that lets anyone redeem the remaining balance) — keep only last 4.
        def _redacted_payment(p: "PaymentEntry") -> dict:
            d = p.model_dump()
            if d.get("gift_card_code"):
                d["gift_card_code"] = "****" + str(d["gift_card_code"])[-4:]
            return d

        payment_breakdown_json = json.dumps(
            [_redacted_payment(p) for p in data.payments], ensure_ascii=False
        )
        methods = [p.method for p in data.payments]
        payment_method = "mixed" if len(set(methods)) > 1 else methods[0]

    # ---- Cash-drawer change helper (ISSUE-074) ----
    # When the cashier records the cash the customer handed over, compute the change
    # owed back. The cash AMOUNT DUE is the cash leg of the sale: the whole charge
    # (incl. tip) for a single cash tender, or the sum of the cash legs of a split.
    # Tendering less than that cash due is rejected — you can't under-pay cash. The
    # change is recorded for the drawer only; it never changes the captured tenders
    # (which still cover the amount due), the invoice total, or the VAT base.
    cash_tendered: Optional[float] = None
    change_due: Optional[float] = None
    if data.cash_tendered is not None:
        cash_tendered = round(float(data.cash_tendered), 2)
        if cash_tendered < 0:
            raise HTTPException(status_code=400, detail="cash_tendered cannot be negative")
        if data.payments:
            cash_due = round(
                sum(p.amount for p in data.payments if (p.method or "") == "cash"), 2
            )
        else:
            cash_due = charge_total if payment_method == "cash" else 0.0
        if cash_tendered + 0.01 < cash_due:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Cash tendered {cash_tendered:.2f} is less than the cash due "
                    f"{cash_due:.2f}"
                ),
            )
        change_due = round(cash_tendered - cash_due, 2)

    # ---- Buyer VAT capture (F-018 / ZA-06) ----
    # A VAT-registered buyer makes this a B2B supply. Prefer the explicit request
    # value (ad-hoc business walk-in); otherwise fall back to the saved customer's
    # VAT number (trusted record, scoped to this user). The captured number is
    # stamped onto the transaction so the invoice buyer block and the
    # clearance/reporting routing are driven by it (see sign_transaction).
    buyer_vat = (data.customer_vat_number or "").strip() or None
    if not buyer_vat and data.customer_id:
        cust = (
            await db.execute(
                select(Customers).where(
                    Customers.id == data.customer_id,
                    Customers.user_id == owner_id,
                )
            )
        ).scalar_one_or_none()
        if cust and (cust.vat_number or "").strip():
            buyer_vat = cust.vat_number.strip()

    # ---- The one fiscal sale path (sale-core extraction, slice 06) ----
    # Hand the normalized cart to services.sale_core.execute_sale, which performs
    # the full atomic sequence — tender capture (PAY-01/05; a card-like leg may
    # name an in-store SoftPOS terminal, HW-03/F-005, and gift-card legs are
    # validated + decremented first, PRC-05/F-038) → invoice counter → inventory
    # deduction (variant/branch/client) → loyalty accrual → shift accumulation →
    # ECDSA sign / hash-chain / archive (ZA-06/ZA-09) — committed together. A
    # decline, short stock or signing failure raises before commit so nothing is
    # persisted (F-001 / POS atomicity). The same core mints the restaurant settle
    # invoice (F-059) and aggregator-ingest sale (F-060). The tenders must capture
    # the full amount due (invoice total + tip, F-012).
    # ---- Combo expansion (ISSUE-066) ----
    # Expand any combo line into its component product lines NOW — after the
    # override/discount/promotion gates ran on the original cart (a combo line has
    # no product_id so it never trips the price-override gate) and right before the
    # sale core. The components re-sum to the bundle price, so subtotal/VAT/total
    # are unchanged, and the sale core deducts each component's stock (ISSUE-032).
    sale_lines = await expand_combo_lines(db, owner_id, data.items)

    result = await execute_sale(
        db,
        NormalizedCart(
            user_id=owner_id,
            client=client,
            lines=sale_lines,
            subtotal=subtotal,
            discount_amount=discount_amount,
            discount_code=(discount_code or None),
            vat_rate=vat_rate,
            vat_amount=vat_amount,
            total_amount=total_amount,
            tender_specs=_build_tender_specs(data, charge_total),
            payment_method=payment_method,
            payment_breakdown_json=payment_breakdown_json,
            tip_amount=tip_amount,
            cash_tendered=cash_tendered,
            change_due=change_due,
            customer_name=data.customer_name,
            customer_phone=data.customer_phone,
            buyer_vat=buyer_vat,
            branch_id=data.branch_id,
            allow_negative_stock=bool(data.allow_negative_stock),
            loyalty_customer_id=data.customer_id,
            loyalty_program=program,
            loyalty_balance=loyalty_balance,
        ),
    )
    transaction = result.transaction
    captured_tenders = result.captured_tenders
    document_id = result.document_id
    stamped_qr = result.stamped_qr
    loyalty_points_earned = result.loyalty_points_earned
    loyalty_balance = result.loyalty_balance

    # Queue Fatoora reporting out-of-band (C-3): fails closed to "pending" when
    # the gateway/onboarding isn't configured; never blocks the committed sale.
    # Skipped entirely when the client has ZATCA disabled (no document to report).
    if document_id is not None:
        background_tasks.add_task(
            zatca_sale.report_document_background, document_id, client.id
        )

    # ---- Domain webhook: sale.completed (Phase 3) ----
    # Fire registered webhooks out-of-band so integrations (accounting, ERP) are
    # notified. Best-effort: a failing endpoint never affects the committed sale.
    background_tasks.add_task(
        fire_event_background,
        owner_id,
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
    await _maybe_send_low_stock_alerts(db, client, sale_lines, background_tasks, owner_id)

    return TransactionResponse(
        id=transaction.id,
        invoice_number=transaction.invoice_number,
        subtotal=transaction.subtotal or 0,
        vat_amount=transaction.vat_amount or 0,
        discount_amount=transaction.discount_amount or 0,
        total_amount=transaction.total_amount,
        tip_amount=transaction.tip_amount or None,
        cash_tendered=transaction.cash_tendered,
        change_due=transaction.change_due,
        payment_method=transaction.payment_method,
        payment_breakdown=transaction.payment_breakdown,
        status=transaction.status or "completed",
        zatca_qr=stamped_qr,
        zatca_qr_base64=(
            zatca_service_mod.render_qr_png_base64(stamped_qr) if stamped_qr else None
        ),
        zatca_hash=transaction.zatca_hash,
        zatca_document_id=document_id,
        zatca_status="signed" if document_id is not None else "disabled",
        items_json=transaction.items_json,
        customer_name=transaction.customer_name,
        customer_phone=transaction.customer_phone,
        created_at=transaction.created_at,
        loyalty_points_earned=loyalty_points_earned or None,
        loyalty_points_redeemed=loyalty_points_redeemed or None,
        loyalty_discount=loyalty_discount or None,
        loyalty_balance=loyalty_balance,
        applied_promotions=[
            AppliedPromotionInfo(
                promotion_id=p.promotion_id, name=p.name, kind=p.kind, amount=p.amount
            )
            for p in applied_promotions
        ] or None,
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
    db: AsyncSession,
    client: Clients,
    items: List["CartItem"],
    background_tasks: Optional[BackgroundTasks] = None,
    owner_id: Optional[str] = None,
) -> None:
    """Dispatch a low-stock alert for any sold product now at/below threshold.

    Sends the merchant email and, when ``background_tasks``/``owner_id`` are
    given, fires the ``product.low_stock`` webhook (ISSUE-051, H25) per affected
    product so integrations can reorder.
    """
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
            if background_tasks is not None and owner_id is not None:
                background_tasks.add_task(
                    fire_event_background,
                    owner_id,
                    "product.low_stock",
                    {
                        "product_id": product.id,
                        "name": product.name,
                        "quantity": product.quantity or 0,
                        "threshold": threshold,
                        "client_id": client.id,
                    },
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
            # POS-11 (F-011): preserve fractional (weighted) quantities on replay.
            quantity=float(it.get("quantity") or 0),
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
    # ZA-09: a replayed offline sale follows the same per-client policy — sign and
    # archive only when the client has ZATCA enabled, otherwise persist the sale
    # without a fiscal document.
    if zatca_sale.is_zatca_enabled(client):
        await zatca_sale.sign_transaction(
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
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """List transactions for the current client, optionally scoped to a branch."""
    client = await get_client_for_user(db, owner_id)

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
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Park the current cart as a ``held`` ticket (POS-10).

    Persists the cart so the cashier can serve another customer and resume this
    one later. No fiscal side effects: the invoice counter is untouched, no ZATCA
    stamp is issued, and stock is not deducted (that all happens when the recalled
    ticket is rung up through ``POST /pos/transaction``).
    """
    logger.info("hold_sale: user=%s items=%d", current_user.id, len(data.items))
    client = await get_client_for_user(db, owner_id)

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
        user_id=owner_id,
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
    skip: int = Query(0, ge=0, description="Rows to skip (pagination offset)"),
    limit: int = Query(50, ge=1, le=200, description="Max held tickets to return"),
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """List the current client's parked (held) tickets, newest first (POS-10).

    Server-side paginated (OPS-05): ``skip``/``limit`` bound the query and ``total``
    is the full count so the held drawer never load-everythings.
    """
    client = await get_client_for_user(db, owner_id)
    filters = (
        Transactions.client_id == client.id,
        Transactions.user_id == owner_id,
        Transactions.status == "held",
    )
    total = (
        await db.execute(select(func.count(Transactions.id)).where(*filters))
    ).scalar() or 0
    result = await db.execute(
        select(Transactions)
        .where(*filters)
        .order_by(Transactions.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    held = result.scalars().all()
    return HeldListResponse(items=[_held_summary(t) for t in held], total=int(total))


@router.post("/recall/{held_id}", response_model=RecallResponse)
async def recall_sale(
    held_id: int,
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Recall a held ticket: return its cart and remove it from the held list.

    The cashier resumes the cart in the POS and rings it up as a fresh sale, so the
    held row is deleted here (not flipped to a sale) — the sale is created normally
    via ``POST /pos/transaction`` with all its fiscal side effects. Owner-scoped: a
    client can only recall its own held tickets (SEC-02).
    """
    client = await get_client_for_user(db, owner_id)
    result = await db.execute(
        select(Transactions).where(
            Transactions.id == held_id,
            Transactions.client_id == client.id,
            Transactions.user_id == owner_id,
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
    # INV-04 (F-033): the variant to return, when the line was a variant SKU. The
    # refund then credits that variant's stock, not the parent product's.
    variant_id: Optional[int] = None


class RefundRequest(BaseModel):
    lines: Optional[List[RefundLine]] = None


def _refund_key(product_id, variant_id) -> tuple:
    """Composite stock-key for refund aggregation: a variant line is tracked apart
    from its parent product so two variants of one product never collapse together
    (INV-04). Product-only sales key as ``(pid, None)`` — identical to the legacy
    per-product behavior."""
    return (int(product_id), int(variant_id) if variant_id else None)


class RefundResponse(BaseModel):
    credit_note_id: int
    original_transaction_id: int
    credit_note_number: str
    total_amount: float
    zatca_qr: Optional[str] = None
    zatca_qr_base64: Optional[str] = None
    # ZA-09: a credit note is only signed/archived when the client has ZATCA
    # enabled; for a ZATCA-disabled client these are null and zatca_status is
    # "disabled".
    zatca_document_id: Optional[int] = None
    zatca_status: str
    # POS-07: "refunded" when every line is now fully returned, "partial_refunded"
    # when a balance remains on the original invoice.
    original_status: str = "refunded"


async def _refunded_quantities(db: AsyncSession, original_id: int) -> dict:
    """Sum already-refunded quantities per (product, variant) across prior credit
    notes that reference ``original_id`` (POS-07). Lets a second partial refund see
    what the first one already returned so the invoice can never be over-refunded.
    Keyed by the composite :func:`_refund_key` so variants are tracked apart (INV-04)."""
    rows = (
        await db.execute(
            select(Transactions).where(
                Transactions.original_transaction_id == original_id,
                Transactions.status == "credit_note",
            )
        )
    ).scalars().all()
    refunded: dict[tuple, float] = {}
    for cn in rows:
        try:
            cn_items = json.loads(cn.items_json) if cn.items_json else []
        except (ValueError, TypeError):
            cn_items = []
        for it in cn_items:
            pid = it.get("product_id")
            if pid is None:
                continue
            key = _refund_key(pid, it.get("variant_id"))
            refunded[key] = refunded.get(key, 0.0) + float(it.get("quantity") or 0)
    return refunded


async def _restore_inventory(db: AsyncSession, client_id: int, items: List[dict]) -> None:
    """Add refunded quantities back to client-level product stock.

    Inverse of ``_deduct_inventory``. Variant lines (INV-04) carry their stock on
    the variant ledger, so they are skipped here and restored by
    :func:`_restore_stock` via ``restore_variant_inventory``.
    """
    # Float so a weighted line (POS-11/F-011) restores the fractional amount sold.
    restore: dict[int, float] = {}
    for item in items:
        if item.get("variant_id"):
            continue
        pid = item.get("product_id")
        if pid:
            restore[pid] = restore.get(pid, 0) + float(item.get("quantity") or 0)
    for product_id, qty in restore.items():
        await db.execute(
            update(Products)
            .where(Products.id == product_id, Products.client_id == client_id)
            .values(quantity=Products.quantity + qty)
        )


async def _restore_stock(
    db: AsyncSession,
    user_id: str,
    client_id: int,
    branch_id: Optional[int],
    items: List[dict],
) -> None:
    """Restore stock for refunded/voided lines to the pool the sale drew from.

    Routes variant lines (INV-04) back to the variant ledger and product lines to
    the branch ledger (when the sale was branch-tagged) or client-level stock,
    mirroring the split on the deduction path so a variant refund/void credits the
    variant — never the parent product.
    """
    variant_items = [it for it in items if it.get("variant_id")]
    product_items = [it for it in items if not it.get("variant_id")]
    if variant_items:
        # A branch-tagged variant sale drew from that branch's variant ledger
        # (ISSUE-067), so credit it back there — never the client-level façade.
        if branch_id:
            from services.variant_branch_stock import restore_variant_branch_inventory

            await restore_variant_branch_inventory(
                db, user_id, client_id, int(branch_id), variant_items
            )
        else:
            from services.product_variants import restore_variant_inventory

            await restore_variant_inventory(db, client_id, variant_items)
    if branch_id:
        from services.branch_stock import restore_branch_inventory

        await restore_branch_inventory(db, user_id, client_id, int(branch_id), product_items)
    else:
        await _restore_inventory(db, client_id, product_items)


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
    owner_id: str = Depends(get_owner_id),
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
    client = await get_client_for_user(db, owner_id)
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

    # Aggregate the original lines by (product, variant) so duplicate lines and
    # per-line discounts collapse to one authoritative entry per SKU. Variants of
    # one product (INV-04) are tracked apart via the composite ``_refund_key`` so
    # each is refunded against its own remaining balance and credited to its own
    # stock ledger.
    orig_by_key: dict[tuple, dict] = {}
    for it in items:
        pid = it.get("product_id")
        if pid is None:
            continue
        key = _refund_key(pid, it.get("variant_id"))
        entry = orig_by_key.setdefault(
            key,
            {"product_id": int(pid), "variant_id": key[1], "name": it.get("name") or "Item",
             "price": float(it.get("price") or 0), "quantity": 0.0, "discount": 0.0},
        )
        entry["quantity"] += float(it.get("quantity") or 0)
        entry["discount"] += float(it.get("discount") or 0)

    already = await _refunded_quantities(db, original.id)

    # Resolve the requested quantities: explicit lines, else the whole remaining
    # balance (legacy whole-invoice refund).
    requested: dict[tuple, float] = {}
    if payload and payload.lines:
        for ln in payload.lines:
            q = float(ln.quantity or 0)
            if q <= 0:
                continue
            key = _refund_key(ln.product_id, ln.variant_id)
            requested[key] = requested.get(key, 0.0) + q
        if not requested:
            raise HTTPException(status_code=400, detail="No refund quantities specified")
    else:
        for key, e in orig_by_key.items():
            remaining = e["quantity"] - already.get(key, 0.0)
            if remaining > 1e-9:
                requested[key] = remaining
        if not requested:
            raise HTTPException(status_code=400, detail="Transaction already refunded")

    # Validate every requested line against what is still refundable.
    for key, q in requested.items():
        if key not in orig_by_key:
            raise HTTPException(
                status_code=400, detail=f"Product {key[0]} is not on the original invoice"
            )
        remaining = orig_by_key[key]["quantity"] - already.get(key, 0.0)
        if q > remaining + 1e-9:
            raise HTTPException(
                status_code=400,
                detail=f"Refund quantity {q} exceeds remaining {remaining} for product {key[0]}",
            )

    # Build the returned-line list (drives stock restore, the credit-note
    # items_json, and the proportional amounts), prorating per-line discounts.
    refund_items: List[dict] = []
    for key, q in requested.items():
        e = orig_by_key[key]
        frac = (q / e["quantity"]) if e["quantity"] else 0.0
        line = {
            "product_id": e["product_id"],
            "name": e["name"],
            "price": e["price"],
            "quantity": q,
            "discount": round(e["discount"] * frac, 4),
        }
        if e["variant_id"]:
            line["variant_id"] = e["variant_id"]
        refund_items.append(line)

    # Prorate the order-level discount/VAT/total by the share of the line subtotal
    # being returned. A full refund (ratio == 1.0) reproduces the original amounts
    # exactly; partial refunds net only their share.
    orig_line_subtotal = sum(
        e["price"] * e["quantity"] - e["discount"] for e in orig_by_key.values()
    )
    refund_line_subtotal = sum(it["price"] * it["quantity"] - it["discount"] for it in refund_items)
    ratio = (refund_line_subtotal / orig_line_subtotal) if orig_line_subtotal else 0.0
    refund_subtotal = round(refund_line_subtotal, 2)
    refund_discount = round((original.discount_amount or 0) * ratio, 2)
    refund_vat = round((original.vat_amount or 0) * ratio, 2)
    refund_total = round((original.total_amount or 0) * ratio, 2)

    # Restore only the returned units to the same stock pool the sale deducted
    # from (branch ledger when branch-tagged, variant ledger for variant lines,
    # else client-level).
    await _restore_stock(
        db, owner_id, client.id, original.branch_id, refund_items
    )

    # Allocate the credit note its own sequential invoice number.
    current_counter = (client.invoice_counter or 0) + 1
    await db.execute(
        update(Clients).where(Clients.id == client.id).values(invoice_counter=current_counter)
    )
    credit_number = f"CRN-{client.id:04d}-{current_counter:06d}"

    credit = Transactions(
        user_id=owner_id,
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
        (already.get(key, 0.0) + requested.get(key, 0.0)) >= e["quantity"] - 1e-9
        for key, e in orig_by_key.items()
    )
    original.status = "refunded" if fully_refunded else "partial_refunded"

    # Net the refund into the open shift (negative amount) so cash reconciles.
    credit.shift_id = await _apply_sale_to_open_shift(
        db, owner_id, credit.total_amount
    )

    await db.flush()

    # PAY-10 / F-004: route the refund back to the original tender(s). Each
    # card-like leg is reversed through the capturing gateway; every reversed leg
    # is recorded as a `refunded` tender on the credit note so the money movement
    # is auditable and the drawer reconciliation can tell the cash portion of a
    # refund from the card portion. A gateway failure rolls the credit note back.
    refund_tender_rows = await _refund_tenders(db, original, refund_total)
    _persist_tenders(db, owner_id, client.id, credit.id, refund_tender_rows)

    # ZA-09: a credit note follows the original sale's per-client policy. With
    # ZATCA on it is a real type-381 ECDSA-signed, hash-chained document; with it
    # off the refund still issues the credit note + reverses tenders/stock, but
    # without a fiscal stamp or zatca_documents row.
    if zatca_sale.is_zatca_enabled(client):
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
    else:
        stamped_qr = None
        document_id = None

    await db.commit()
    await db.refresh(credit)

    if document_id is not None:
        background_tasks.add_task(zatca_sale.report_document_background, document_id, client.id)
    background_tasks.add_task(
        fire_event_background,
        owner_id,
        "sale.refunded",
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
        zatca_qr_base64=(
            zatca_service_mod.render_qr_png_base64(stamped_qr) if stamped_qr else None
        ),
        zatca_document_id=document_id,
        zatca_status="signed" if document_id is not None else "disabled",
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
    owner_id: str = Depends(get_owner_id),
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
    client = await get_client_for_user(db, owner_id)
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

    # Restore stock to the same pool the sale deducted from (branch- and
    # variant-aware): variant lines (INV-04) credit the variant ledger.
    try:
        items = json.loads(txn.items_json) if txn.items_json else []
    except (ValueError, TypeError):
        items = []
    await _restore_stock(db, owner_id, client.id, txn.branch_id, items)

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
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Render the ZATCA tax invoice as an **always-Arabic** print-ready document.

    The receipts/quotations-always-Arabic rule (SRS §7) is enforced here: the
    document is rendered RTL/Arabic regardless of the caller's UI language. The
    returned HTML is print-to-PDF ready in any browser; wire a headless renderer
    (e.g. WeasyPrint) in front of this for server-side PDF bytes.
    """
    client = await get_client_for_user(db, owner_id)
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
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Return the tax invoice as real ``application/pdf`` bytes (Phase 6 PDF).

    Rendered server-side with the fiscal ZATCA QR embedded. The frontend offers
    this as a "Download PDF" action on receipts/invoices.
    """
    from fastapi.responses import Response

    from services.pdf_render import invoice_pdf_bytes

    client = await get_client_for_user(db, owner_id)
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
    reprint: bool = Query(
        False,
        description="Reprint a past sale: stamp the receipt as a duplicate copy and audit it.",
    ),
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Return a base64 ESC/POS byte stream for thermal printing (Phase E).

    The frontend streams the decoded bytes to a WebUSB / Web Bluetooth thermal
    printer. The embedded QR is the canonical ZATCA TLV payload, so the printed
    receipt carries the same fiscal QR as the always-Arabic HTML invoice.

    ISSUE-075 (reprint past receipts): with ``reprint=true`` the cashier reprints
    a *past* sale. The receipt is re-rendered from the stored sale data through
    the same renderer — template, totals and QR all match the original — but the
    body is stamped *نسخة — إعادة طباعة* ("copy — reprint") so the duplicate can
    never be mistaken for the original tax invoice, and the reprint is recorded
    in ``audit_logs`` (fraud control, mirroring the void audit trail).
    """
    client = await get_client_for_user(db, owner_id)
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

    # H26 (#45): render through the merchant's default receipt template so its
    # header/footer/logo/show_qr/font_size knobs actually reach the printout.
    template = await load_default_template(db, owner_id)

    # H26/U5.2 (#47): route to the merchant's saved/selected receipt printer. A
    # printer's paper_size overrides the template's so the raster matches the
    # actual head, and the resolved device is echoed back so the browser streams
    # to the right printer instead of re-prompting for any USB device.
    printer = await resolve_printer(db, owner_id, "receipt")
    if printer is not None and printer.paper_size:
        template = {**(template or {}), "paper_size": printer.paper_size}

    # ISSUE-079: the merchant's store-settings receipt footer feeds the printed
    # receipt. A footer set on the receipt-template still wins (it is the more
    # specific knob); the store-settings footer fills in when the template leaves
    # it blank, so the merchant-level default reaches the printout.
    store = await get_store_settings(db, owner_id)
    if store is not None and (store.receipt_footer or "").strip():
        if not (template or {}).get("footer_text"):
            template = {**(template or {}), "footer_text": store.receipt_footer.strip()}

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
        tip_amount=txn.tip_amount or 0,
        zatca_qr=txn.zatca_qr or "",
        open_drawer=open_drawer,
        reprint=reprint,
        template=template,
    )

    # ISSUE-075: a reprint of a past sale is audited for fraud control (a duplicate
    # fiscal document leaving the printer is a sensitive action, like a void).
    if reprint:
        db.add(
            Audit_logs(
                user_id=str(current_user.id),
                action="POS_REPRINT_RECEIPT",
                entity_type="transactions",
                entity_id=str(txn.id),
                details=f"Reprinted receipt for sale {txn.invoice_number}",
            )
        )
        await db.commit()

    return {
        "invoice_number": txn.invoice_number,
        "format": "escpos",
        "encoding": "base64",
        "data": payload,
        "printer": (
            {
                "id": printer.id,
                "name": printer.name,
                "device_id": printer.device_id,
                "paper_size": printer.paper_size,
            }
            if printer is not None
            else None
        ),
    }


@router.post(
    "/transactions/{txn_id}/email",
    dependencies=[Depends(require_feature("email_receipts"))],
)
async def email_invoice_receipt(
    txn_id: int,
    data: EmailReceiptRequest,
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Email a receipt for a transaction (POS-04).

    Gated by the per-client ``email_receipts`` feature flag (AG-03): an agent can
    disable receipt emailing for a specific client. Uses the EmailService
    (stub-logs until SMTP is configured).
    """
    client = await get_client_for_user(db, owner_id)
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
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Send a transaction receipt by SMS (POS-04).

    Gated by the per-client ``sms_receipts`` feature flag (AG-03). Uses the Twilio
    transport (``core.sms``) when configured and otherwise logs in dev mode; the
    ``delivered`` flag tells the caller which path ran.
    """
    from core.sms import send_sms

    client = await get_client_for_user(db, owner_id)
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
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """List the per-branch stock ledger for a branch (branch-scoped stock report)."""
    from services.branch_stock import list_branch_stock

    client = await get_client_for_user(db, owner_id)
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
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Allocate/adjust a product's stock for a specific branch."""
    from services.branch_stock import set_branch_stock

    client = await get_client_for_user(db, owner_id)
    row = await set_branch_stock(
        db, owner_id, client.id, branch_id, data.product_id, data.quantity
    )
    return {
        "branch_id": branch_id,
        "product_id": row.product_id,
        "quantity": row.quantity,
    }


# ---------- Per-branch variant stock ledger (ISSUE-067) ----------
class VariantBranchStockSetRequest(BaseModel):
    variant_id: int
    quantity: int


@router.get("/branches/{branch_id}/variant-stock")
async def get_branch_variant_stock(
    branch_id: int,
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """List the per-branch variant-stock ledger for a branch (INV-03 × INV-04)."""
    from services.variant_branch_stock import list_variant_branch_stock

    client = await get_client_for_user(db, owner_id)
    rows = await list_variant_branch_stock(db, client.id, branch_id)
    return {
        "branch_id": branch_id,
        "items": [
            {"variant_id": r.variant_id, "quantity": r.quantity} for r in rows
        ],
        "total": len(rows),
    }


@router.put("/branches/{branch_id}/variant-stock")
async def set_branch_variant_stock_endpoint(
    branch_id: int,
    data: VariantBranchStockSetRequest,
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Allocate/adjust a variant's stock for a specific branch."""
    from services.variant_branch_stock import set_variant_branch_stock

    client = await get_client_for_user(db, owner_id)
    row = await set_variant_branch_stock(
        db, owner_id, client.id, branch_id, data.variant_id, data.quantity
    )
    return {
        "branch_id": branch_id,
        "variant_id": row.variant_id,
        "quantity": row.quantity,
    }