import base64
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.auth import get_current_user
from schemas.auth import UserResponse
from models.clients import Clients
from models.products import Products
from models.transactions import Transactions

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/pos", tags=["pos"])


# ---------- Pydantic Schemas ----------
class CartItem(BaseModel):
    product_id: int
    name: str
    price: float
    quantity: int
    discount: Optional[float] = 0


class CreateTransactionRequest(BaseModel):
    items: List[CartItem]
    payment_method: str  # "cash", "card", "mixed"
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    discount_amount: Optional[float] = 0
    vat_rate: Optional[float] = 15.0  # Default 15% VAT for Saudi Arabia
    # When False (default) a sale is rejected if any line exceeds available stock.
    # The sale and the stock deduction are committed together in one transaction.
    allow_negative_stock: Optional[bool] = False


class TransactionResponse(BaseModel):
    id: int
    invoice_number: str
    subtotal: float
    vat_amount: float
    discount_amount: float
    total_amount: float
    payment_method: str
    status: str
    zatca_qr: Optional[str] = None
    zatca_hash: Optional[str] = None
    items_json: Optional[str] = None
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    created_at: Optional[datetime] = None


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
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new POS transaction with ZATCA QR code generation."""
    client = await get_client_for_user(db, str(current_user.id))

    # Calculate totals
    subtotal = 0.0
    for item in data.items:
        item_total = item.price * item.quantity - (item.discount or 0)
        subtotal += item_total

    discount_amount = data.discount_amount or 0
    taxable_amount = subtotal - discount_amount
    vat_rate = data.vat_rate if data.vat_rate is not None else 15.0
    vat_amount = round(taxable_amount * (vat_rate / 100), 2)
    total_amount = round(taxable_amount + vat_amount, 2)

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

    # Generate ZATCA QR code
    seller_name = client.business_name or "Business"
    vat_number = client.vat_number or "000000000000000"

    zatca_qr = generate_zatca_tlv(
        seller_name=seller_name,
        vat_number=vat_number,
        timestamp=timestamp_iso,
        total_with_vat=f"{total_amount:.2f}",
        vat_amount=f"{vat_amount:.2f}",
    )

    # Generate ZATCA hash
    invoice_data = {
        "invoice_number": invoice_number,
        "seller_name": seller_name,
        "vat_number": vat_number,
        "timestamp": timestamp_iso,
        "subtotal": subtotal,
        "discount": discount_amount,
        "vat_amount": vat_amount,
        "total_amount": total_amount,
        "items": [item.model_dump() for item in data.items],
    }
    zatca_hash = generate_zatca_hash(invoice_data)

    # Create transaction record
    transaction = Transactions(
        user_id=str(current_user.id),
        client_id=client.id,
        invoice_number=invoice_number,
        subtotal=subtotal,
        vat_amount=vat_amount,
        discount_amount=discount_amount,
        total_amount=total_amount,
        payment_method=data.payment_method,
        status="completed",
        zatca_qr=zatca_qr,
        zatca_hash=zatca_hash,
        items_json=items_json,
        customer_name=data.customer_name,
        customer_phone=data.customer_phone,
    )
    db.add(transaction)

    # ---- Atomic inventory deduction (same transaction as the sale) ----
    # The sale, the invoice-counter increment, and every stock decrement are
    # committed together. If stock is insufficient (and overselling isn't
    # allowed) we raise before commit, so nothing is persisted and the counter
    # is not consumed — fixing the previous fire-and-forget deduction gap.
    await _deduct_inventory(db, client.id, data.items, bool(data.allow_negative_stock))

    await db.commit()
    await db.refresh(transaction)

    return TransactionResponse(
        id=transaction.id,
        invoice_number=transaction.invoice_number,
        subtotal=transaction.subtotal or 0,
        vat_amount=transaction.vat_amount or 0,
        discount_amount=transaction.discount_amount or 0,
        total_amount=transaction.total_amount,
        payment_method=transaction.payment_method,
        status=transaction.status or "completed",
        zatca_qr=transaction.zatca_qr,
        zatca_hash=transaction.zatca_hash,
        items_json=transaction.items_json,
        customer_name=transaction.customer_name,
        customer_phone=transaction.customer_phone,
        created_at=transaction.created_at,
    )


@router.get("/transactions", response_model=TransactionListResponse)
async def list_transactions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List transactions for the current client with pagination."""
    client = await get_client_for_user(db, str(current_user.id))

    offset = (page - 1) * page_size

    # Get total count
    count_result = await db.execute(
        select(func.count(Transactions.id))
        .where(Transactions.client_id == client.id)
    )
    total = count_result.scalar() or 0

    # Get paginated transactions
    result = await db.execute(
        select(Transactions)
        .where(Transactions.client_id == client.id)
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