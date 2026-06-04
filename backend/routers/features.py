import csv
import io
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import select, func, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db, db_manager
from dependencies.auth import get_current_user
from dependencies.features import require_feature
from schemas.auth import UserResponse
from models.auth import User
from models.agents import Agents
from models.clients import Clients
from models.products import Products
from models.transactions import Transactions
from models.packages import Packages
from models.notifications import Notifications

logger = logging.getLogger(__name__)

router = APIRouter(tags=["features"])


# ---------- Helper: Determine user role ----------
async def get_user_role(db: AsyncSession, user_id: str) -> dict:
    """Determine user role based on database records."""
    result = await db.execute(select(Agents).where(Agents.user_id == user_id))
    agent = result.scalar_one_or_none()
    if agent:
        return {"role": "agent", "entity_id": agent.id, "agent_id": None}

    result = await db.execute(select(Clients).where(Clients.user_id == user_id))
    client = result.scalar_one_or_none()
    if client:
        return {"role": "client", "entity_id": client.id, "agent_id": client.agent_id}

    # Only explicitly-seeded admins act as the platform master. Any other
    # account without an agent/client record is treated as a least-privilege
    # client (prevents self-registered users from becoming master). Mirrors
    # tenant.py::get_user_role — SEC-02 least-privilege.
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if user and user.role == "admin":
        return {"role": "master", "entity_id": None, "agent_id": None}

    return {"role": "client", "entity_id": None, "agent_id": None}


# ============================================================
# PRODUCT MANAGEMENT
# ============================================================

class ProductCreateRequest(BaseModel):
    name: str
    name_ar: Optional[str] = None
    barcode: Optional[str] = None
    price: float
    cost_price: Optional[float] = None
    quantity: Optional[int] = 0
    category: Optional[str] = None
    vat_rate: Optional[float] = 15.0


class ProductUpdateRequest(BaseModel):
    name: Optional[str] = None
    name_ar: Optional[str] = None
    barcode: Optional[str] = None
    price: Optional[float] = None
    cost_price: Optional[float] = None
    quantity: Optional[int] = None
    category: Optional[str] = None
    vat_rate: Optional[float] = None
    is_active: Optional[bool] = None


class ProductResponse(BaseModel):
    id: int
    client_id: int
    name: str
    name_ar: Optional[str] = None
    barcode: Optional[str] = None
    price: float
    cost_price: Optional[float] = None
    quantity: int
    category: Optional[str] = None
    vat_rate: Optional[float] = None
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ProductListResponse(BaseModel):
    items: List[ProductResponse]
    total: int


@router.get("/api/v1/products/list", response_model=ProductListResponse)
async def list_products(
    category: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List products for current client with optional filters."""
    role_info = await get_user_role(db, str(current_user.id))
    if role_info["role"] != "client":
        raise HTTPException(status_code=403, detail="Only clients can access products")

    client_id = role_info["entity_id"]
    query = select(Products).where(Products.client_id == client_id)

    if category:
        query = query.where(Products.category == category)
    if search:
        query = query.where(Products.name.ilike(f"%{search}%"))

    # Count
    count_query = select(func.count(Products.id)).where(Products.client_id == client_id)
    if category:
        count_query = count_query.where(Products.category == category)
    if search:
        count_query = count_query.where(Products.name.ilike(f"%{search}%"))

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    result = await db.execute(
        query.order_by(Products.created_at.desc()).offset(skip).limit(limit)
    )
    products = result.scalars().all()

    items = [
        ProductResponse(
            id=p.id,
            client_id=p.client_id,
            name=p.name,
            name_ar=p.name_ar,
            barcode=p.barcode,
            price=p.price,
            cost_price=p.cost_price,
            quantity=p.quantity or 0,
            category=p.category,
            vat_rate=p.vat_rate,
            is_active=p.is_active if p.is_active is not None else True,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
        for p in products
    ]

    return ProductListResponse(items=items, total=total)


@router.post("/api/v1/products/create", response_model=ProductResponse)
async def create_product(
    data: ProductCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new product for the current client."""
    role_info = await get_user_role(db, str(current_user.id))
    if role_info["role"] != "client":
        raise HTTPException(status_code=403, detail="Only clients can create products")

    client_id = role_info["entity_id"]

    product = Products(
        user_id=str(current_user.id),
        client_id=client_id,
        name=data.name,
        name_ar=data.name_ar,
        barcode=data.barcode,
        price=data.price,
        cost_price=data.cost_price,
        quantity=data.quantity or 0,
        category=data.category,
        vat_rate=data.vat_rate if data.vat_rate is not None else 15.0,
        is_active=True,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)

    return ProductResponse(
        id=product.id,
        client_id=product.client_id,
        name=product.name,
        name_ar=product.name_ar,
        barcode=product.barcode,
        price=product.price,
        cost_price=product.cost_price,
        quantity=product.quantity or 0,
        category=product.category,
        vat_rate=product.vat_rate,
        is_active=True,
        created_at=product.created_at,
        updated_at=product.updated_at,
    )


@router.put("/api/v1/products/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: int,
    data: ProductUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a product (client only)."""
    role_info = await get_user_role(db, str(current_user.id))
    if role_info["role"] != "client":
        raise HTTPException(status_code=403, detail="Only clients can update products")

    client_id = role_info["entity_id"]

    result = await db.execute(
        select(Products).where(
            and_(Products.id == product_id, Products.client_id == client_id)
        )
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    update_data = data.model_dump(exclude_unset=True)
    if update_data:
        await db.execute(
            update(Products)
            .where(and_(Products.id == product_id, Products.client_id == client_id))
            .values(**update_data)
        )
        await db.commit()
        await db.refresh(product)

    return ProductResponse(
        id=product.id,
        client_id=product.client_id,
        name=product.name,
        name_ar=product.name_ar,
        barcode=product.barcode,
        price=product.price,
        cost_price=product.cost_price,
        quantity=product.quantity or 0,
        category=product.category,
        vat_rate=product.vat_rate,
        is_active=product.is_active if product.is_active is not None else True,
        created_at=product.created_at,
        updated_at=product.updated_at,
    )


@router.delete("/api/v1/products/{product_id}")
async def delete_product(
    product_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Deactivate a product (soft delete)."""
    role_info = await get_user_role(db, str(current_user.id))
    if role_info["role"] != "client":
        raise HTTPException(status_code=403, detail="Only clients can delete products")

    client_id = role_info["entity_id"]

    result = await db.execute(
        select(Products).where(
            and_(Products.id == product_id, Products.client_id == client_id)
        )
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    await db.execute(
        update(Products)
        .where(and_(Products.id == product_id, Products.client_id == client_id))
        .values(is_active=False)
    )
    await db.commit()

    return {"success": True, "message": "Product deactivated"}


@router.get("/api/v1/products/low-stock", response_model=ProductListResponse)
async def get_low_stock_products(
    threshold: int = Query(10, ge=1),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get products with quantity below threshold."""
    role_info = await get_user_role(db, str(current_user.id))
    if role_info["role"] != "client":
        raise HTTPException(status_code=403, detail="Only clients can access products")

    client_id = role_info["entity_id"]

    result = await db.execute(
        select(Products).where(
            and_(
                Products.client_id == client_id,
                Products.quantity < threshold,
                Products.is_active == True,
            )
        ).order_by(Products.quantity.asc())
    )
    products = result.scalars().all()

    items = [
        ProductResponse(
            id=p.id,
            client_id=p.client_id,
            name=p.name,
            name_ar=p.name_ar,
            barcode=p.barcode,
            price=p.price,
            cost_price=p.cost_price,
            quantity=p.quantity or 0,
            category=p.category,
            vat_rate=p.vat_rate,
            is_active=True,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
        for p in products
    ]

    return ProductListResponse(items=items, total=len(items))


# ============================================================
# INVENTORY
# ============================================================

class InventoryDeductItem(BaseModel):
    product_id: int
    quantity: int


class InventoryDeductRequest(BaseModel):
    items: List[InventoryDeductItem]


class InventoryAlertItem(BaseModel):
    id: int
    name: str
    quantity: int
    category: Optional[str] = None


class InventoryAlertsResponse(BaseModel):
    items: List[InventoryAlertItem]
    total: int


@router.post(
    "/api/v1/inventory/deduct",
    deprecated=True,
    dependencies=[Depends(require_feature("inventory"))],
)
async def deduct_inventory(
    data: InventoryDeductRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """DEPRECATED: stock is now deducted atomically inside POST /api/v1/pos/transaction.

    Kept for backward compatibility / manual stock adjustments only. Do not call
    this after creating a transaction or stock will be double-deducted.
    """
    role_info = await get_user_role(db, str(current_user.id))
    if role_info["role"] != "client":
        raise HTTPException(status_code=403, detail="Only clients can deduct inventory")

    client_id = role_info["entity_id"]
    deducted = []

    for item in data.items:
        result = await db.execute(
            select(Products).where(
                and_(Products.id == item.product_id, Products.client_id == client_id)
            )
        )
        product = result.scalar_one_or_none()
        if not product:
            continue

        new_qty = max(0, (product.quantity or 0) - item.quantity)
        await db.execute(
            update(Products)
            .where(Products.id == item.product_id)
            .values(quantity=new_qty)
        )
        deducted.append({"product_id": item.product_id, "new_quantity": new_qty})

    await db.commit()

    return {"success": True, "deducted": deducted}


@router.get(
    "/api/v1/inventory/alerts",
    response_model=InventoryAlertsResponse,
    dependencies=[Depends(require_feature("inventory"))],
)
async def get_inventory_alerts(
    threshold: int = Query(10, ge=1),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get low stock alerts (products below threshold)."""
    role_info = await get_user_role(db, str(current_user.id))
    if role_info["role"] != "client":
        raise HTTPException(status_code=403, detail="Only clients can access inventory alerts")

    client_id = role_info["entity_id"]

    result = await db.execute(
        select(Products).where(
            and_(
                Products.client_id == client_id,
                Products.quantity < threshold,
                Products.is_active == True,
            )
        ).order_by(Products.quantity.asc())
    )
    products = result.scalars().all()

    items = [
        InventoryAlertItem(
            id=p.id,
            name=p.name,
            quantity=p.quantity or 0,
            category=p.category,
        )
        for p in products
    ]

    return InventoryAlertsResponse(items=items, total=len(items))


# ============================================================
# AGENT BRANDING
# ============================================================

class BrandingUpdateRequest(BaseModel):
    logo_url: Optional[str] = None
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    font_family: Optional[str] = None
    button_radius: Optional[str] = None
    # Agent's default UI language propagated to their clients (L10N-05).
    default_language: Optional[str] = None


class BrandingUpdateResponse(BaseModel):
    success: bool
    logo_url: Optional[str] = None
    primary_color: str
    secondary_color: str
    font_family: str
    button_radius: str
    default_language: str = "en"


@router.put("/api/v1/branding/update", response_model=BrandingUpdateResponse)
async def update_agent_branding(
    data: BrandingUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update agent branding settings."""
    role_info = await get_user_role(db, str(current_user.id))
    if role_info["role"] != "agent":
        raise HTTPException(status_code=403, detail="Only agents can update branding")

    agent_id = role_info["entity_id"]

    update_data = data.model_dump(exclude_unset=True)
    if update_data:
        await db.execute(
            update(Agents).where(Agents.id == agent_id).values(**update_data)
        )
        await db.commit()

    # Fetch updated agent
    result = await db.execute(select(Agents).where(Agents.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    return BrandingUpdateResponse(
        success=True,
        logo_url=agent.logo_url,
        primary_color=agent.primary_color or "#3B82F6",
        secondary_color=agent.secondary_color or "#1E40AF",
        font_family=agent.font_family or "Inter",
        button_radius=agent.button_radius or "8px",
        default_language=agent.default_language or "en",
    )


# ============================================================
# REPORTS & ANALYTICS
# ============================================================

class SalesSummaryItem(BaseModel):
    period: str
    total_sales: float
    transaction_count: int
    avg_transaction: float


class SalesSummaryResponse(BaseModel):
    items: List[SalesSummaryItem]
    total_sales: float
    total_transactions: int


def _period_bucket(dialect_name: str, period: str):
    """SQL expression bucketing ``created_at`` into a period key.

    Pushed into the database so the report aggregate runs as a single
    ``GROUP BY`` instead of pulling every transaction into Python and grouping
    in a loop (OPS-05 — server-side aggregation, no load-everything). Date
    formatting is dialect-specific (sqlite ``strftime`` vs postgres ``to_char``),
    so we branch on the active dialect.
    """
    col = Transactions.created_at
    if dialect_name == "sqlite":
        fmt = {"daily": "%Y-%m-%d", "weekly": "%Y-W%W", "monthly": "%Y-%m"}[period]
        return func.strftime(fmt, col)
    # PostgreSQL (and other ``to_char``-capable dialects). ``IW``/``IYYY`` give
    # the ISO week so weekly buckets line up with the calendar week.
    fmt = {"daily": "YYYY-MM-DD", "weekly": 'IYYY-"W"IW', "monthly": "YYYY-MM"}[period]
    return func.to_char(col, fmt)


class TopProductItem(BaseModel):
    product_id: int
    name: str
    total_quantity_sold: int
    total_revenue: float


class TopProductsResponse(BaseModel):
    items: List[TopProductItem]


@router.get("/api/v1/reports/sales-summary", response_model=SalesSummaryResponse)
async def get_sales_summary(
    period: str = Query("daily", pattern="^(daily|weekly|monthly)$"),
    days: int = Query(30, ge=1, le=365),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get sales summary grouped by period for current client."""
    role_info = await get_user_role(db, str(current_user.id))
    if role_info["role"] != "client":
        raise HTTPException(status_code=403, detail="Only clients can access reports")

    client_id = role_info["entity_id"]
    start_date = datetime.now(timezone.utc) - timedelta(days=days)

    # OPS-05: aggregate in the database (one GROUP BY) rather than loading every
    # transaction in the window into memory and grouping in Python. The result
    # set is bounded by the number of distinct periods (<= ``days``), not by the
    # transaction count, so this stays flat as a client's volume grows.
    dialect_name = db_manager.engine.dialect.name if db_manager.engine is not None else "sqlite"
    bucket = _period_bucket(dialect_name, period)
    result = await db.execute(
        select(
            bucket.label("period"),
            func.coalesce(func.sum(Transactions.total_amount), 0.0).label("total"),
            func.count().label("cnt"),
        ).where(
            and_(
                Transactions.client_id == client_id,
                Transactions.created_at >= start_date,
                # POS-10/POS-08: parked (held) tickets and voided sales are not
                # revenue — exclude them so neither inflates reported sales.
                # ``is_distinct_from`` keeps NULL-status (legacy completed) rows.
                Transactions.status.is_distinct_from("held"),
                Transactions.status.is_distinct_from("voided"),
            )
        ).group_by(bucket).order_by(bucket)
    )
    rows = result.all()

    items: List[SalesSummaryItem] = []
    total_sales = 0.0
    total_transactions = 0
    for period_key, total, count in rows:
        total = float(total or 0)
        count = int(count or 0)
        items.append(
            SalesSummaryItem(
                period=period_key,
                total_sales=round(total, 2),
                transaction_count=count,
                avg_transaction=round(total / count, 2) if count > 0 else 0,
            )
        )
        total_sales += total
        total_transactions += count

    return SalesSummaryResponse(
        items=items,
        total_sales=round(total_sales, 2),
        total_transactions=total_transactions,
    )


@router.get("/api/v1/reports/top-products", response_model=TopProductsResponse)
async def get_top_products(
    limit: int = Query(10, ge=1, le=50),
    days: int = Query(30, ge=1, le=365),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get top selling products by quantity sold."""
    role_info = await get_user_role(db, str(current_user.id))
    if role_info["role"] != "client":
        raise HTTPException(status_code=403, detail="Only clients can access reports")

    client_id = role_info["entity_id"]
    start_date = datetime.now(timezone.utc) - timedelta(days=days)

    # OPS-05: the per-product totals live inside each transaction's ``items_json``
    # blob, so this cannot collapse into a pure SQL GROUP BY portably. Instead we
    # stream the window through a server-side cursor (selecting only the JSON
    # column, never the full ORM row) and fold each transaction into a bounded
    # accumulator keyed by product — so peak memory is O(distinct products), not
    # O(transactions), and we never materialize the whole period at once.
    product_sales: dict = {}
    result = await db.stream_scalars(
        select(Transactions.items_json).where(
            and_(
                Transactions.client_id == client_id,
                Transactions.created_at >= start_date,
                # POS-10/POS-08: exclude parked (held) tickets and voided sales
                # from top-products (NULL-status legacy rows are kept).
                Transactions.status.is_distinct_from("held"),
                Transactions.status.is_distinct_from("voided"),
            )
        )
    )
    async for items_json in result:
        if not items_json:
            continue
        try:
            items = json.loads(items_json)
        except (json.JSONDecodeError, TypeError):
            continue
        for item in items:
            pid = item.get("product_id", 0)
            qty = item.get("quantity", 0)
            price = item.get("price", 0)
            name = item.get("name", "Unknown")
            if pid not in product_sales:
                product_sales[pid] = {"name": name, "quantity": 0, "revenue": 0.0}
            product_sales[pid]["quantity"] += qty
            product_sales[pid]["revenue"] += price * qty

    # Sort by quantity and take top N
    sorted_products = sorted(
        product_sales.items(), key=lambda x: x[1]["quantity"], reverse=True
    )[:limit]

    items = [
        TopProductItem(
            product_id=pid,
            name=data["name"],
            total_quantity_sold=data["quantity"],
            total_revenue=round(data["revenue"], 2),
        )
        for pid, data in sorted_products
    ]

    return TopProductsResponse(items=items)


@router.get("/api/v1/reports/export-csv")
async def export_transactions_csv(
    days: int = Query(30, ge=1, le=365),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export transactions as CSV text."""
    role_info = await get_user_role(db, str(current_user.id))
    if role_info["role"] != "client":
        raise HTTPException(status_code=403, detail="Only clients can export reports")

    client_id = role_info["entity_id"]
    start_date = datetime.now(timezone.utc) - timedelta(days=days)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Invoice Number", "Date", "Subtotal", "VAT", "Discount",
        "Total", "Payment Method", "Status", "Customer Name", "Customer Phone"
    ])

    # OPS-05: stream the rows through a server-side cursor and write each as we
    # go, rather than materializing the whole period into a Python list first.
    row_count = 0
    result = await db.stream_scalars(
        select(Transactions).where(
            and_(
                Transactions.client_id == client_id,
                Transactions.created_at >= start_date,
                # POS-10/POS-08: exclude parked (held) tickets and voided sales
                # from the sales CSV export (the void itself is in audit_logs).
                Transactions.status.is_distinct_from("held"),
                Transactions.status.is_distinct_from("voided"),
            )
        ).order_by(Transactions.created_at.desc())
    )
    async for t in result:
        writer.writerow([
            t.invoice_number,
            t.created_at.isoformat() if t.created_at else "",
            t.subtotal or 0,
            t.vat_amount or 0,
            t.discount_amount or 0,
            t.total_amount,
            t.payment_method,
            t.status or "completed",
            t.customer_name or "",
            t.customer_phone or "",
        ])
        row_count += 1

    return {"csv_content": output.getvalue(), "row_count": row_count}


# ============================================================
# PAYMENT-METHOD BREAKDOWN (RPT-03) — how a period's revenue was tendered
# ============================================================
# Groups a date window's captured tenders by method (cash / mada / card /
# applepay / stcpay / tabby / tamara / transfer / loyalty) from the real
# ``payment_tenders`` rows (F-001) — not the ``payment_method`` label. ``refunds``
# is the amount reversed back to that tender (refund-to-origin, F-004), so ``net``
# is what each method actually collected for the period. Aggregated in SQL (one
# GROUP BY, bounded by the number of distinct tender types) — never the OPS-05
# load-everything anti-pattern.


class PaymentBreakdownTender(BaseModel):
    tender_type: str
    collected: float
    refunds: float
    net: float
    count: int


class PaymentBreakdownResponse(BaseModel):
    days: int
    tenders: List[PaymentBreakdownTender]
    total_collected: float
    total_refunds: float
    net: float


@router.get("/api/v1/reports/payment-breakdown", response_model=PaymentBreakdownResponse)
async def get_payment_breakdown(
    days: int = Query(30, ge=1, le=365),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Payment-method breakdown for the period (RPT-03).

    Sales-by-tender and refunds-by-tender from the captured ``payment_tenders``
    rows (F-001/F-004), grouped per method. Card-like legs carry a real approval,
    so the breakdown is what the merchant truly collected per method — not a sum
    of method labels. ``net = collected - refunds``.
    """
    role_info = await get_user_role(db, str(current_user.id))
    if role_info["role"] != "client":
        raise HTTPException(status_code=403, detail="Only clients can access reports")

    client_id = role_info["entity_id"]
    start_date = datetime.now(timezone.utc) - timedelta(days=days)

    from models.payment_tenders import PaymentTenders

    # OPS-05: aggregate in the database. One GROUP BY over the (already lean)
    # tenders table keyed by (tender_type, status); the result set is bounded by
    # the number of distinct tender types, never the transaction count, so this
    # stays flat as a client's volume grows.
    result = await db.execute(
        select(
            PaymentTenders.tender_type,
            PaymentTenders.status,
            func.coalesce(func.sum(PaymentTenders.amount), 0.0).label("amount"),
            func.count().label("cnt"),
        ).where(
            and_(
                PaymentTenders.client_id == client_id,
                PaymentTenders.created_at >= start_date,
                PaymentTenders.status != "declined",
            )
        ).group_by(PaymentTenders.tender_type, PaymentTenders.status)
    )

    buckets: dict = {}
    for tender_type, status, amount, cnt in result.all():
        key = tender_type or "unknown"
        bucket = buckets.setdefault(key, {"collected": 0.0, "refunds": 0.0, "count": 0})
        amount = float(amount or 0)
        if status == "refunded":
            # Money reversed back to this tender (refund-to-origin, F-004).
            bucket["refunds"] += amount
        else:  # captured / authorized — money taken in on a sale
            bucket["collected"] += amount
            bucket["count"] += int(cnt or 0)

    tenders = [
        PaymentBreakdownTender(
            tender_type=k,
            collected=round(v["collected"], 2),
            refunds=round(v["refunds"], 2),
            net=round(v["collected"] - v["refunds"], 2),
            count=v["count"],
        )
        for k, v in buckets.items()
    ]
    # Largest net contributor first; ties broken by name for a deterministic order.
    tenders.sort(key=lambda t: (-t.net, t.tender_type))

    total_collected = round(sum(t.collected for t in tenders), 2)
    total_refunds = round(sum(t.refunds for t in tenders), 2)

    return PaymentBreakdownResponse(
        days=days,
        tenders=tenders,
        total_collected=total_collected,
        total_refunds=total_refunds,
        net=round(total_collected - total_refunds, 2),
    )


# ============================================================
# Z-REPORT / X-REPORT (RPT-06, PRN-05) — fiscal day-close
# ============================================================
# A Z-report reconciles a single shift: sales grouped by tender (the real
# captured ``payment_tenders`` rows from F-001, not labels), VAT collected vs
# reversed, discounts, voids, refunds, and — critically — the cash drawer
# (expected vs counted + variance) computed against **cash tenders only**, not
# gross sales. Run against an open shift it is an X-report (mid-shift, no
# counted cash yet); against a closed shift it is the Z-report emitted on close.


class ZReportTender(BaseModel):
    tender_type: str
    amount: float
    count: int


class ZReportShiftInfo(BaseModel):
    id: int
    staff_name: Optional[str] = None
    branch_id: Optional[int] = None
    status: str
    opening_cash: float
    closing_cash: Optional[float] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None


class ZReportTotals(BaseModel):
    gross_sales: float
    refunds: float
    net_sales: float
    discounts: float
    vat_collected: float
    vat_reversed: float
    net_vat: float
    sale_count: int
    refund_count: int
    void_count: int
    voids: float


class ZReportCash(BaseModel):
    opening_cash: float
    cash_sales: float
    cash_refunds: float
    expected_cash: float
    counted_cash: Optional[float] = None
    variance: Optional[float] = None
    reconciliation: Optional[str] = None


class ZReportResponse(BaseModel):
    report_type: str  # "Z" (closed shift) or "X" (open shift)
    shift: ZReportShiftInfo
    totals: ZReportTotals
    tenders: List[ZReportTender]
    cash: ZReportCash


async def _resolve_shift(db: AsyncSession, user_id: str, shift_id: Optional[int]):
    """Resolve the target shift: the given id (scoped to the caller) or, when
    omitted, the caller's currently open shift (X-report). Returns the Shifts row
    or None."""
    from models.shifts import Shifts

    if shift_id is not None:
        result = await db.execute(
            select(Shifts).where(Shifts.id == shift_id, Shifts.user_id == user_id)
        )
        return result.scalar_one_or_none()

    result = await db.execute(
        select(Shifts).where(Shifts.user_id == user_id, Shifts.status == "open")
    )
    return result.scalar_one_or_none()


async def _aggregate_zreport(db: AsyncSession, client_id: int, shift) -> dict:
    """Aggregate one shift's transactions into the Z/X-report structure.

    Sales-by-tender is built from the real ``payment_tenders`` rows (F-001); a
    sale predating tender capture falls back to its ``payment_method`` so legacy
    data still reconciles. Cash variance uses cash tenders only (the POS-09 fix
    point) — gross sales are **not** treated as drawer cash.
    """
    from models.payment_tenders import PaymentTenders
    from services.production import compute_shift_cash_reconciliation

    txn_result = await db.execute(
        select(Transactions).where(
            and_(
                Transactions.shift_id == shift.id,
                Transactions.client_id == client_id,
            )
        )
    )
    transactions = txn_result.scalars().all()

    gross_sales = 0.0
    refunds_total = 0.0
    vat_collected = 0.0
    vat_reversed = 0.0
    discounts = 0.0
    voids_total = 0.0
    sale_count = 0
    refund_count = 0
    void_count = 0
    sale_ids: List[int] = []

    for t in transactions:
        status = t.status or "completed"
        if status == "credit_note":
            refunds_total += abs(float(t.total_amount or 0))
            vat_reversed += abs(float(t.vat_amount or 0))
            refund_count += 1
        elif status == "voided":
            voids_total += abs(float(t.total_amount or 0))
            void_count += 1
        else:  # completed / refunded / partial_refunded — original sale rows
            gross_sales += float(t.total_amount or 0)
            vat_collected += float(t.vat_amount or 0)
            discounts += float(t.discount_amount or 0)
            sale_count += 1
            sale_ids.append(t.id)

    # Real captured tenders for the sale rows, grouped per transaction.
    tenders_by_txn: dict = {}
    if sale_ids:
        tender_result = await db.execute(
            select(PaymentTenders).where(
                and_(
                    PaymentTenders.transaction_id.in_(sale_ids),
                    PaymentTenders.status != "declined",
                )
            )
        )
        for tr in tender_result.scalars().all():
            tenders_by_txn.setdefault(tr.transaction_id, []).append(tr)

    tender_totals: dict = {}
    for t in transactions:
        status = t.status or "completed"
        if status in ("credit_note", "voided"):
            continue
        rows = tenders_by_txn.get(t.id)
        if rows:
            for tr in rows:
                bucket = tender_totals.setdefault(
                    tr.tender_type or "unknown", {"amount": 0.0, "count": 0}
                )
                bucket["amount"] += float(tr.amount or 0)
                bucket["count"] += 1
        else:
            # Legacy sale without captured tenders: attribute to its method.
            ttype = t.payment_method or "unknown"
            bucket = tender_totals.setdefault(ttype, {"amount": 0.0, "count": 0})
            bucket["amount"] += float(t.total_amount or 0)
            bucket["count"] += 1

    tenders = [
        {"tender_type": k, "amount": round(v["amount"], 2), "count": v["count"]}
        for k, v in sorted(tender_totals.items())
    ]

    # Cash drawer reconciliation — cash tenders only (POS-09). Delegated to the
    # shared helper so the report and the stored shift (close_shift, F-009) agree
    # exactly. With refund-to-origin wired (F-004), only the cash leg of a refund
    # is cash paid out of the drawer; a card refund is reversed to the card.
    recon = await compute_shift_cash_reconciliation(db, shift)
    cash_sales = recon["cash_sales"]
    cash_refunds = recon["cash_refunds"]
    expected_cash = recon["expected_cash"]
    counted_cash = shift.closing_cash if shift.status == "closed" else None
    variance = (
        round(counted_cash - expected_cash, 2) if counted_cash is not None else None
    )
    reconciliation = None
    if variance is not None:
        reconciliation = (
            "balanced" if abs(variance) < 0.01 else ("over" if variance > 0 else "short")
        )

    return {
        "report_type": "Z" if shift.status == "closed" else "X",
        "shift": {
            "id": shift.id,
            "staff_name": shift.staff_name,
            "branch_id": shift.branch_id,
            "status": shift.status,
            "opening_cash": shift.opening_cash or 0,
            "closing_cash": shift.closing_cash,
            "start_time": shift.start_time,
            "end_time": shift.end_time,
        },
        "totals": {
            "gross_sales": round(gross_sales, 2),
            "refunds": round(refunds_total, 2),
            "net_sales": round(gross_sales - refunds_total, 2),
            "discounts": round(discounts, 2),
            "vat_collected": round(vat_collected, 2),
            "vat_reversed": round(vat_reversed, 2),
            "net_vat": round(vat_collected - vat_reversed, 2),
            "sale_count": sale_count,
            "refund_count": refund_count,
            "void_count": void_count,
            "voids": round(voids_total, 2),
        },
        "tenders": tenders,
        "cash": {
            "opening_cash": round(shift.opening_cash or 0, 2),
            "cash_sales": cash_sales,
            "cash_refunds": cash_refunds,
            "expected_cash": expected_cash,
            "counted_cash": counted_cash,
            "variance": variance,
            "reconciliation": reconciliation,
        },
    }


@router.get("/api/v1/reports/zreport", response_model=ZReportResponse)
async def get_zreport(
    shift_id: Optional[int] = Query(None, description="Shift to report on; omit for the current open shift"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Z-report (closed shift) / X-report (open shift): tenders, VAT, discounts,
    voids, refunds and cash variance for a single shift (RPT-06)."""
    role_info = await get_user_role(db, str(current_user.id))
    if role_info["role"] != "client":
        raise HTTPException(status_code=403, detail="Only clients can access reports")

    client_id = role_info["entity_id"]
    shift = await _resolve_shift(db, str(current_user.id), shift_id)
    if not shift:
        detail = "Shift not found" if shift_id is not None else "No open shift to report on"
        raise HTTPException(status_code=404, detail=detail)

    data = await _aggregate_zreport(db, client_id, shift)
    return ZReportResponse(**data)


@router.get("/api/v1/reports/zreport/document", response_class=HTMLResponse)
async def get_zreport_document(
    shift_id: Optional[int] = Query(None, description="Shift to print; omit for the current open shift"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Render the Z/X-report as an **always-Arabic** print-ready document (PRN-05).

    Enforces the fiscal/management-document Arabic rule (SRS §7) server-side: the
    report renders RTL/Arabic regardless of the caller's UI language. Print-to-PDF
    ready in any browser (80mm or A4)."""
    from services.production import PDFInvoiceService

    role_info = await get_user_role(db, str(current_user.id))
    if role_info["role"] != "client":
        raise HTTPException(status_code=403, detail="Only clients can access reports")

    client_id = role_info["entity_id"]
    shift = await _resolve_shift(db, str(current_user.id), shift_id)
    if not shift:
        detail = "Shift not found" if shift_id is not None else "No open shift to report on"
        raise HTTPException(status_code=404, detail=detail)

    data = await _aggregate_zreport(db, client_id, shift)

    client_row = (
        await db.execute(select(Clients).where(Clients.id == client_id))
    ).scalar_one_or_none()
    business_name = client_row.business_name if client_row else "—"

    html = PDFInvoiceService.generate_zreport_html(business_name=business_name, data=data)
    return HTMLResponse(content=html)


# ============================================================
# NOTIFICATIONS (persisted — UX-08 / F-052)
# ============================================================
# The feed used to be synthesized per-request with a no-op ``mark-read`` (read
# state was a lie across reloads) and a field mismatch (``items`` vs
# ``notifications``) that meant the page never rendered anything. It is now backed
# by the persisted ``notifications`` table: system alerts (IB §UX-08 feed:
# low-stock / ZATCA-failed / subscription) are *materialized idempotently* by a
# stable ``dedupe_key`` so re-materialization preserves ``is_read``, and
# ``mark-read`` flips the stored flag — so an acknowledgment survives a refetch.
# Every read/write is scoped to ``user_id`` (SEC-02).


class NotificationItem(BaseModel):
    id: str
    type: str  # "low_stock", "zatca_failed", "subscription", "system"
    title: str
    message: str
    is_read: bool
    created_at: str


class NotificationsResponse(BaseModel):
    items: List[NotificationItem]
    unread_count: int


class MarkReadRequest(BaseModel):
    # Acknowledge a single notification; omit to mark the caller's whole feed read.
    notification_id: Optional[str] = None


async def _upsert_notification(
    db: AsyncSession,
    *,
    user_id: str,
    client_id: Optional[int],
    type: str,
    title: str,
    message: str,
    dedupe_key: str,
) -> None:
    """Insert a system alert, or refresh an existing one in place.

    Keyed by ``(user_id, dedupe_key)`` so repeated materialization never
    duplicates a row and — critically — **preserves the stored ``is_read``** so a
    "mark as read" survives the next refetch. Only the message/title are refreshed
    to the current state (e.g. the live low-stock quantity).
    """
    existing = (
        await db.execute(
            select(Notifications).where(
                and_(
                    Notifications.user_id == user_id,
                    Notifications.dedupe_key == dedupe_key,
                )
            )
        )
    ).scalar_one_or_none()

    if existing:
        existing.title = title
        existing.message = message
    else:
        db.add(Notifications(
            user_id=user_id,
            client_id=client_id,
            type=type,
            title=title,
            message=message,
            dedupe_key=dedupe_key,
            is_read=False,
        ))


async def _materialize_notifications(db: AsyncSession, user_id: str, client_id: int) -> None:
    """Idempotently materialize the IB §UX-08 alert feed for a client.

    Sources: low-stock products, stuck ZATCA documents (pending/failed), and an
    overdue subscription. Each is upserted by ``dedupe_key`` so the persisted
    read-state is preserved. Best-effort per source (broad except) so one failing
    source never blanks the whole feed (OPS-08 graceful degradation).
    """
    # --- Low stock (INV-08-ish alerting) ---
    try:
        low_stock = (
            await db.execute(
                select(Products).where(
                    and_(
                        Products.client_id == client_id,
                        Products.quantity < 10,
                        Products.is_active == True,
                    )
                ).limit(20)
            )
        ).scalars().all()
        for p in low_stock:
            await _upsert_notification(
                db,
                user_id=user_id,
                client_id=client_id,
                type="low_stock",
                title="Low Stock Alert",
                message=f"{p.name} has only {p.quantity or 0} units remaining",
                dedupe_key=f"low_stock:{p.id}",
            )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to materialize low-stock notifications: %s", exc)

    # --- ZATCA documents stuck pending/failed (ZA-08 alerting) ---
    try:
        from models.zatca_documents import ZatcaDocuments

        stuck = (
            await db.execute(
                select(
                    ZatcaDocuments.status,
                    func.count().label("cnt"),
                ).where(
                    and_(
                        ZatcaDocuments.client_id == client_id,
                        ZatcaDocuments.status.in_(("pending", "failed")),
                    )
                ).group_by(ZatcaDocuments.status)
            )
        ).all()
        for status, cnt in stuck:
            if cnt:
                await _upsert_notification(
                    db,
                    user_id=user_id,
                    client_id=client_id,
                    type="zatca_failed",
                    title="ZATCA Documents Need Attention",
                    message=f"{cnt} invoice(s) are {status} with ZATCA",
                    dedupe_key=f"zatca:{status}",
                )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to materialize ZATCA notifications: %s", exc)

    # --- Overdue subscription (CL-06 alerting) ---
    try:
        merchant = (
            await db.execute(select(Clients).where(Clients.id == client_id))
        ).scalar_one_or_none()
        if merchant and merchant.subscription_status in ("past_due", "suspended"):
            await _upsert_notification(
                db,
                user_id=user_id,
                client_id=client_id,
                type="subscription",
                title="Subscription Payment Due",
                message=f"Your subscription is {merchant.subscription_status} — please settle to avoid suspension",
                dedupe_key="subscription:status",
            )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to materialize subscription notifications: %s", exc)


@router.get("/api/v1/notifications/list", response_model=NotificationsResponse)
async def get_notifications(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the persisted notification feed for the current user (UX-08).

    For a client, refresh the system-alert feed first (idempotent upsert by
    ``dedupe_key`` — preserves read state), then return every persisted row owned
    by this user, newest first.
    """
    user_id = str(current_user.id)
    role_info = await get_user_role(db, user_id)

    if role_info["role"] == "client":
        await _materialize_notifications(db, user_id, role_info["entity_id"])
        await db.commit()

    rows = (
        await db.execute(
            select(Notifications)
            .where(Notifications.user_id == user_id)
            .order_by(Notifications.is_read.asc(), Notifications.created_at.desc())
        )
    ).scalars().all()

    items = [
        NotificationItem(
            id=str(n.id),
            type=n.type,
            title=n.title or "",
            message=n.message,
            is_read=bool(n.is_read),
            created_at=n.created_at.isoformat() if n.created_at else "",
        )
        for n in rows
    ]
    unread_count = sum(1 for n in rows if not n.is_read)

    return NotificationsResponse(items=items, unread_count=unread_count)


@router.post("/api/v1/notifications/mark-read")
async def mark_notifications_read(
    payload: MarkReadRequest = MarkReadRequest(),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Persist a read acknowledgment (UX-08).

    With a ``notification_id``, mark that one row read; without one, mark the
    caller's whole feed read. Scoped to ``user_id`` so a client can only
    acknowledge their own notifications — acknowledging a row that isn't theirs (or
    doesn't exist) is a 404 (SEC-02).
    """
    user_id = str(current_user.id)

    if payload.notification_id is not None:
        try:
            target_id = int(payload.notification_id)
        except (TypeError, ValueError):
            raise HTTPException(status_code=404, detail="Notification not found")

        row = (
            await db.execute(
                select(Notifications).where(
                    and_(
                        Notifications.id == target_id,
                        Notifications.user_id == user_id,
                    )
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="Notification not found")
        row.is_read = True
        await db.commit()
        return {"success": True, "message": "Notification marked as read"}

    await db.execute(
        update(Notifications)
        .where(and_(Notifications.user_id == user_id, Notifications.is_read == False))
        .values(is_read=True)
    )
    await db.commit()
    return {"success": True, "message": "All notifications marked as read"}


# ============================================================
# PACKAGE MANAGEMENT (Master Admin only)
# ============================================================

class PackageCreateRequest(BaseModel):
    name: str
    client_slots: int
    wholesale_price: float
    suggested_retail_price: Optional[float] = None
    is_active: Optional[bool] = True


class PackageUpdateRequest(BaseModel):
    name: Optional[str] = None
    client_slots: Optional[int] = None
    wholesale_price: Optional[float] = None
    suggested_retail_price: Optional[float] = None
    is_active: Optional[bool] = None


class PackageResponse(BaseModel):
    id: int
    name: str
    client_slots: int
    wholesale_price: float
    suggested_retail_price: Optional[float] = None
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class PackageListResponse(BaseModel):
    items: List[PackageResponse]
    total: int


@router.get("/api/v1/packages/list", response_model=PackageListResponse)
async def list_packages(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all packages (master admin only)."""
    role_info = await get_user_role(db, str(current_user.id))
    if role_info["role"] != "master":
        raise HTTPException(status_code=403, detail="Only master admin can manage packages")

    result = await db.execute(
        select(Packages).order_by(Packages.created_at.desc())
    )
    packages = result.scalars().all()

    items = [
        PackageResponse(
            id=p.id,
            name=p.name,
            client_slots=p.client_slots,
            wholesale_price=p.wholesale_price,
            suggested_retail_price=p.suggested_retail_price,
            is_active=p.is_active if p.is_active is not None else True,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
        for p in packages
    ]

    return PackageListResponse(items=items, total=len(items))


@router.post("/api/v1/packages/create", response_model=PackageResponse)
async def create_package(
    data: PackageCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new package (master admin only)."""
    role_info = await get_user_role(db, str(current_user.id))
    if role_info["role"] != "master":
        raise HTTPException(status_code=403, detail="Only master admin can manage packages")

    package = Packages(
        name=data.name,
        client_slots=data.client_slots,
        wholesale_price=data.wholesale_price,
        suggested_retail_price=data.suggested_retail_price,
        is_active=data.is_active if data.is_active is not None else True,
    )
    db.add(package)
    await db.commit()
    await db.refresh(package)

    return PackageResponse(
        id=package.id,
        name=package.name,
        client_slots=package.client_slots,
        wholesale_price=package.wholesale_price,
        suggested_retail_price=package.suggested_retail_price,
        is_active=package.is_active if package.is_active is not None else True,
        created_at=package.created_at,
        updated_at=package.updated_at,
    )


@router.put("/api/v1/packages/{package_id}", response_model=PackageResponse)
async def update_package(
    package_id: int,
    data: PackageUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a package (master admin only)."""
    role_info = await get_user_role(db, str(current_user.id))
    if role_info["role"] != "master":
        raise HTTPException(status_code=403, detail="Only master admin can manage packages")

    result = await db.execute(select(Packages).where(Packages.id == package_id))
    package = result.scalar_one_or_none()
    if not package:
        raise HTTPException(status_code=404, detail="Package not found")

    update_data = data.model_dump(exclude_unset=True)
    if update_data:
        await db.execute(
            update(Packages).where(Packages.id == package_id).values(**update_data)
        )
        await db.commit()
        await db.refresh(package)

    return PackageResponse(
        id=package.id,
        name=package.name,
        client_slots=package.client_slots,
        wholesale_price=package.wholesale_price,
        suggested_retail_price=package.suggested_retail_price,
        is_active=package.is_active if package.is_active is not None else True,
        created_at=package.created_at,
        updated_at=package.updated_at,
    )


@router.delete("/api/v1/packages/{package_id}")
async def delete_package(
    package_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Deactivate a package (soft delete, master admin only)."""
    role_info = await get_user_role(db, str(current_user.id))
    if role_info["role"] != "master":
        raise HTTPException(status_code=403, detail="Only master admin can manage packages")

    result = await db.execute(select(Packages).where(Packages.id == package_id))
    package = result.scalar_one_or_none()
    if not package:
        raise HTTPException(status_code=404, detail="Package not found")

    await db.execute(
        update(Packages).where(Packages.id == package_id).values(is_active=False)
    )
    await db.commit()

    return {"success": True, "message": "Package deactivated"}