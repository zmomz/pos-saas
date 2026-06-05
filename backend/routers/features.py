import csv
import io
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import select, func, update, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db, db_manager
from dependencies.auth import get_current_user
from dependencies.features import require_feature
from services.packages import normalize_feature_tier, parse_feature_tier
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
    # POS-11 (F-011): Float so weighted products carry fractional on-hand stock.
    quantity: Optional[float] = 0
    # INV-08 (F-035): per-product reorder point + suggested order amount.
    reorder_point: Optional[int] = 0
    reorder_quantity: Optional[int] = 0
    category: Optional[str] = None
    vat_rate: Optional[float] = 15.0
    # POS-11 (F-011): weighted / open-price configuration.
    is_weighted: Optional[bool] = False
    is_open_price: Optional[bool] = False
    unit_label: Optional[str] = None


class ProductUpdateRequest(BaseModel):
    name: Optional[str] = None
    name_ar: Optional[str] = None
    barcode: Optional[str] = None
    price: Optional[float] = None
    cost_price: Optional[float] = None
    quantity: Optional[float] = None
    reorder_point: Optional[int] = None
    reorder_quantity: Optional[int] = None
    category: Optional[str] = None
    vat_rate: Optional[float] = None
    is_active: Optional[bool] = None
    # POS-11 (F-011): weighted / open-price configuration.
    is_weighted: Optional[bool] = None
    is_open_price: Optional[bool] = None
    unit_label: Optional[str] = None


class ProductResponse(BaseModel):
    id: int
    client_id: int
    name: str
    name_ar: Optional[str] = None
    barcode: Optional[str] = None
    price: float
    cost_price: Optional[float] = None
    quantity: float
    reorder_point: int = 0
    reorder_quantity: int = 0
    category: Optional[str] = None
    vat_rate: Optional[float] = None
    is_active: bool
    # POS-11 (F-011): weighted / open-price configuration.
    is_weighted: bool = False
    is_open_price: bool = False
    unit_label: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


def _low_stock_clause(default_threshold: int):
    """INV-08 (F-035): a product is low-stock when on-hand <= its configured
    ``reorder_point`` (when set > 0); otherwise it falls back to the fixed
    ``default_threshold`` (legacy behaviour for products with no reorder point).
    """
    qty = func.coalesce(Products.quantity, 0)
    rp = func.coalesce(Products.reorder_point, 0)
    return or_(
        and_(rp > 0, qty <= rp),
        and_(rp <= 0, qty < default_threshold),
    )


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
            reorder_point=p.reorder_point or 0,
            reorder_quantity=p.reorder_quantity or 0,
            category=p.category,
            vat_rate=p.vat_rate,
            is_active=p.is_active if p.is_active is not None else True,
            is_weighted=bool(p.is_weighted),
            is_open_price=bool(p.is_open_price),
            unit_label=p.unit_label,
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
        reorder_point=data.reorder_point or 0,
        reorder_quantity=data.reorder_quantity or 0,
        category=data.category,
        vat_rate=data.vat_rate if data.vat_rate is not None else 15.0,
        is_active=True,
        # POS-11 (F-011): weighted / open-price configuration.
        is_weighted=bool(data.is_weighted),
        is_open_price=bool(data.is_open_price),
        unit_label=data.unit_label,
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
        reorder_point=product.reorder_point or 0,
        reorder_quantity=product.reorder_quantity or 0,
        category=product.category,
        vat_rate=product.vat_rate,
        is_active=True,
        is_weighted=bool(product.is_weighted),
        is_open_price=bool(product.is_open_price),
        unit_label=product.unit_label,
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
        reorder_point=product.reorder_point or 0,
        reorder_quantity=product.reorder_quantity or 0,
        category=product.category,
        vat_rate=product.vat_rate,
        is_active=product.is_active if product.is_active is not None else True,
        is_weighted=bool(product.is_weighted),
        is_open_price=bool(product.is_open_price),
        unit_label=product.unit_label,
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
    """Get low-stock products.

    INV-08 (F-035): a product is low when on-hand <= its per-product
    ``reorder_point`` (when configured); products without a reorder point fall
    back to the fixed ``threshold`` query param (legacy behaviour).
    """
    role_info = await get_user_role(db, str(current_user.id))
    if role_info["role"] != "client":
        raise HTTPException(status_code=403, detail="Only clients can access products")

    client_id = role_info["entity_id"]

    result = await db.execute(
        select(Products).where(
            and_(
                Products.client_id == client_id,
                _low_stock_clause(threshold),
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
            reorder_point=p.reorder_point or 0,
            reorder_quantity=p.reorder_quantity or 0,
            category=p.category,
            vat_rate=p.vat_rate,
            is_active=True,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
        for p in products
    ]

    return ProductListResponse(items=items, total=len(items))


class ReorderSuggestion(BaseModel):
    product_id: int
    name: str
    name_ar: Optional[str] = None
    category: Optional[str] = None
    on_hand: int
    reorder_point: int
    reorder_quantity: int
    suggested_order_quantity: int


class ReorderSuggestionsResponse(BaseModel):
    items: List[ReorderSuggestion]
    total: int


@router.get("/api/v1/products/reorder-suggestions", response_model=ReorderSuggestionsResponse)
async def get_reorder_suggestions(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """INV-08 (F-035): auto-PO suggestions for products at/below their reorder point.

    Only products with an explicit ``reorder_point`` (> 0) whose on-hand has
    fallen to or below it are returned — the auto-PO surface is opt-in per
    product. The suggested order quantity is the product's ``reorder_quantity``
    when set, otherwise enough to bring stock back above the reorder point.
    """
    role_info = await get_user_role(db, str(current_user.id))
    if role_info["role"] != "client":
        raise HTTPException(status_code=403, detail="Only clients can access products")

    client_id = role_info["entity_id"]

    qty = func.coalesce(Products.quantity, 0)
    rp = func.coalesce(Products.reorder_point, 0)
    result = await db.execute(
        select(Products).where(
            and_(
                Products.client_id == client_id,
                Products.is_active == True,
                rp > 0,
                qty <= rp,
            )
        ).order_by(Products.quantity.asc())
    )
    products = result.scalars().all()

    items = []
    for p in products:
        on_hand = p.quantity or 0
        point = p.reorder_point or 0
        order_qty = p.reorder_quantity or 0
        # Without an explicit reorder quantity, suggest enough to climb back
        # above the reorder point (at least one unit when triggered).
        suggested = order_qty if order_qty > 0 else max(point - on_hand + 1, 1)
        items.append(
            ReorderSuggestion(
                product_id=p.id,
                name=p.name,
                name_ar=p.name_ar,
                category=p.category,
                on_hand=on_hand,
                reorder_point=point,
                reorder_quantity=order_qty,
                suggested_order_quantity=suggested,
            )
        )

    return ReorderSuggestionsResponse(items=items, total=len(items))


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
    """Get low stock alerts (reorder-point aware; falls back to threshold)."""
    role_info = await get_user_role(db, str(current_user.id))
    if role_info["role"] != "client":
        raise HTTPException(status_code=403, detail="Only clients can access inventory alerts")

    client_id = role_info["entity_id"]

    result = await db.execute(
        select(Products).where(
            and_(
                Products.client_id == client_id,
                _low_stock_clause(threshold),
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
            reorder_point=p.reorder_point or 0,
            reorder_quantity=p.reorder_quantity or 0,
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
    # AG-05: the agent's custom domain ("" / null clears it). Normalized + checked
    # for uniqueness before persisting.
    custom_domain: Optional[str] = None
    # AG-06: the agent's branded provisioning-email template (optional).
    email_template_subject: Optional[str] = None
    email_template_body: Optional[str] = None


class BrandingUpdateResponse(BaseModel):
    success: bool
    logo_url: Optional[str] = None
    primary_color: str
    secondary_color: str
    font_family: str
    button_radius: str
    default_language: str = "en"
    custom_domain: Optional[str] = None


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

    # AG-05: a custom domain is normalized (lowercase, no scheme/port/www) and must
    # be unique across agents — two resellers can't claim the same host. An empty
    # value clears it. Imported here to avoid a circular import at module load.
    if "custom_domain" in update_data:
        from routers.tenant import normalize_domain

        normalized = normalize_domain(update_data["custom_domain"])
        if normalized:
            clash = await db.execute(
                select(Agents.id).where(
                    func.lower(Agents.custom_domain) == normalized,
                    Agents.id != agent_id,
                )
            )
            if clash.scalar_one_or_none() is not None:
                raise HTTPException(
                    status_code=409, detail="This domain is already in use by another agent"
                )
        update_data["custom_domain"] = normalized

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
        custom_domain=getattr(agent, "custom_domain", None),
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
# ACCOUNTING JOURNAL / GENERAL-LEDGER EXPORT (FIN-02, P1)
# ============================================================
# The accountant hand-off (IB §4.11): a standard double-entry journal for a
# period — sales revenue, VAT payable, COGS, inventory, and the cash/bank legs
# by tender — that a bookkeeper imports into Zoho/QuickBooks/Odoo by hand until
# the direct-push integrations (FIN-03) land. It is a *period-summary* journal
# (one balanced set of GL lines for the window), built so that
# **Σ debits == Σ credits by construction**:
#
#   Cash & bank (by tender) ......... Dr  net money in (sales − refunds)
#   Sales Revenue ................... Cr  total − VAT
#   VAT Payable ..................... Cr  VAT collected − reversed
#   Cost of Goods Sold .............. Dr  COGS of sold − returned units
#   Inventory ....................... Cr  same COGS amount
#
# Because the revenue line is derived as ``total − VAT`` (not from the raw
# subtotal), the cash side and the revenue+VAT side reconcile to the exact same
# figure regardless of per-line rounding; and COGS Dr always equals Inventory
# Cr. Credit notes (refunds) carry negative signed amounts (F-007), so they net
# down each account on the same lines. Aggregated server-side — the cash/VAT/
# revenue legs in SQL, COGS by streaming each transaction's ``items_json`` once
# against a bounded product-cost map (OPS-05, never load-everything).

# Standard chart-of-accounts codes used by the journal. Kept stable so a repeat
# export maps to the same GL accounts the bookkeeper already created.
_GL_SALES_REVENUE = ("4000", "Sales Revenue")
_GL_VAT_PAYABLE = ("2100", "VAT Payable")
_GL_COGS = ("5000", "Cost of Goods Sold")
_GL_INVENTORY = ("1300", "Inventory")
_GL_CASH_ON_HAND = ("1010", "Cash on Hand")

# Maps a captured tender type to the GL cash/bank account it settles into. Cash
# hits the till; everything card-like/wallet/BNPL settles through a bank/clearing
# account; transfers and internal tenders get their own lines.
_TENDER_GL_ACCOUNTS = {
    "cash": ("1010", "Cash on Hand"),
    "mada": ("1020", "Card/Wallet Clearing"),
    "card": ("1020", "Card/Wallet Clearing"),
    "applepay": ("1020", "Card/Wallet Clearing"),
    "stcpay": ("1020", "Card/Wallet Clearing"),
    "tabby": ("1025", "BNPL Receivable"),
    "tamara": ("1025", "BNPL Receivable"),
    "transfer": ("1030", "Bank Transfer"),
    "loyalty": ("4050", "Loyalty/Other Settlement"),
}


def _tender_gl_account(tender_type: Optional[str]):
    return _TENDER_GL_ACCOUNTS.get((tender_type or "").lower(), _GL_CASH_ON_HAND)


class JournalLine(BaseModel):
    account_code: str
    account: str
    description: str
    debit: float
    credit: float


class JournalExportResponse(BaseModel):
    days: int
    from_date: str
    to_date: str
    lines: List[JournalLine]
    total_debit: float
    total_credit: float
    balanced: bool
    csv_content: str


@router.get("/api/v1/reports/journal-export", response_model=JournalExportResponse)
async def export_accounting_journal(
    days: int = Query(30, ge=1, le=365),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Accounting journal / general-ledger export for the period (FIN-02).

    A balanced double-entry journal (sales / VAT / COGS / inventory / payments-by
    -tender) for the trailing ``days`` window. ``Σ debit == Σ credit`` by
    construction; voided and held rows are excluded (neither is realized
    revenue), credit notes net the accounts down via their negative amounts.
    """
    role_info = await get_user_role(db, str(current_user.id))
    if role_info["role"] != "client":
        raise HTTPException(status_code=403, detail="Only clients can export the accounting journal")

    client_id = role_info["entity_id"]
    now = datetime.now(timezone.utc)
    start_date = now - timedelta(days=days)

    # ---- Revenue + VAT (signed sums over the window) ----
    # POS-10/POS-08: parked (held) tickets and voided sales are not realized
    # revenue. ``is_distinct_from`` keeps NULL-status (legacy completed) rows.
    not_excluded = and_(
        Transactions.status.is_distinct_from("held"),
        Transactions.status.is_distinct_from("voided"),
    )
    totals = (
        await db.execute(
            select(
                func.coalesce(func.sum(Transactions.total_amount), 0.0),
                func.coalesce(func.sum(Transactions.vat_amount), 0.0),
            ).where(
                and_(
                    Transactions.client_id == client_id,
                    Transactions.created_at >= start_date,
                    not_excluded,
                )
            )
        )
    ).one()
    gross_total = round(float(totals[0] or 0.0), 2)
    vat_total = round(float(totals[1] or 0.0), 2)
    # Revenue is derived as (total − VAT) so the cash side and the revenue+VAT
    # side reconcile to the exact same figure regardless of per-line rounding.
    revenue_total = round(gross_total - vat_total, 2)

    # ---- Payments by tender (the cash/bank debit legs) ----
    # Net per method from the real captured ``payment_tenders`` rows (F-001):
    # captured legs add, refunded legs (F-004) subtract. Aggregated in SQL.
    from models.payment_tenders import PaymentTenders

    tender_rows = (
        await db.execute(
            select(
                PaymentTenders.tender_type,
                PaymentTenders.status,
                func.coalesce(func.sum(PaymentTenders.amount), 0.0),
            ).where(
                and_(
                    PaymentTenders.client_id == client_id,
                    PaymentTenders.created_at >= start_date,
                    PaymentTenders.status != "declined",
                )
            ).group_by(PaymentTenders.tender_type, PaymentTenders.status)
        )
    ).all()

    tender_net: dict = {}
    for tender_type, status, amount, in tender_rows:
        amount = float(amount or 0.0)
        signed = -amount if status == "refunded" else amount
        tender_net[tender_type or "cash"] = tender_net.get(tender_type or "cash", 0.0) + signed

    tenders_total = round(sum(tender_net.values()), 2)
    # Sales without a captured tender row (legacy / cash-only installs) leave a
    # remainder between the money the sales say was taken (``gross_total``) and
    # what the tender ledger accounts for; book it to Cash on Hand so the cash
    # side always reconciles to the revenue+VAT side exactly.
    cash_remainder = round(gross_total - tenders_total, 2)

    # ---- COGS (stream items_json once against a bounded cost map) ----
    cost_rows = (
        await db.execute(
            select(Products.id, Products.cost_price).where(Products.client_id == client_id)
        )
    ).all()
    cost_map = {pid: float(cost or 0.0) for pid, cost in cost_rows}

    cogs_total = 0.0
    stream = await db.stream(
        select(Transactions.items_json, Transactions.status).where(
            and_(
                Transactions.client_id == client_id,
                Transactions.created_at >= start_date,
                not_excluded,
            )
        )
    )
    async for items_json, status in stream:
        if not items_json:
            continue
        try:
            items = json.loads(items_json)
        except (json.JSONDecodeError, TypeError):
            continue
        # A credit note's returned lines carry positive quantities (F-007) but
        # reverse COGS, so flip the sign for refunds.
        sign = -1.0 if status == "credit_note" else 1.0
        for item in items:
            cost = cost_map.get(item.get("product_id", 0), 0.0)
            cogs_total += sign * cost * float(item.get("quantity", 0) or 0)
    cogs_total = round(cogs_total, 2)

    # ---- Assemble the balanced journal ----
    lines: List[JournalLine] = []

    def _add(account, description, amount):
        """Add a signed amount to its natural side (Dr if >= 0, else Cr)."""
        code, name = account
        amount = round(float(amount), 2)
        if amount == 0:
            return
        lines.append(
            JournalLine(
                account_code=code,
                account=name,
                description=description,
                debit=amount if amount > 0 else 0.0,
                credit=-amount if amount < 0 else 0.0,
            )
        )

    # Cash/bank legs by tender (natural debit), then the legacy remainder.
    for tender_type in sorted(tender_net):
        _add(
            _tender_gl_account(tender_type),
            f"Payments received — {tender_type}",
            tender_net[tender_type],
        )
    _add(_GL_CASH_ON_HAND, "Cash sales (untendered remainder)", cash_remainder)
    # Revenue + VAT (natural credit → negative signed amounts).
    _add(_GL_SALES_REVENUE, "Net sales revenue (ex-VAT)", -revenue_total)
    _add(_GL_VAT_PAYABLE, "Output VAT collected", -vat_total)
    # COGS / inventory (Dr COGS, Cr inventory of the same amount).
    _add(_GL_COGS, "Cost of goods sold", cogs_total)
    _add(_GL_INVENTORY, "Inventory consumed", -cogs_total)

    total_debit = round(sum(line.debit for line in lines), 2)
    total_credit = round(sum(line.credit for line in lines), 2)
    balanced = abs(total_debit - total_credit) < 0.01

    # CSV in the same shape ExpenseTracking/Reports already download.
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Account Code", "Account", "Description", "Debit", "Credit"])
    period_label = f"{start_date.date().isoformat()}..{now.date().isoformat()}"
    for line in lines:
        writer.writerow([
            period_label,
            line.account_code,
            line.account,
            line.description,
            f"{line.debit:.2f}",
            f"{line.credit:.2f}",
        ])
    writer.writerow([period_label, "", "TOTAL", "", f"{total_debit:.2f}", f"{total_credit:.2f}"])

    return JournalExportResponse(
        days=days,
        from_date=start_date.date().isoformat(),
        to_date=now.date().isoformat(),
        lines=lines,
        total_debit=total_debit,
        total_credit=total_credit,
        balanced=balanced,
        csv_content=output.getvalue(),
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
    # POS-13 (F-012): gratuities collected over the shift, on top of the invoice
    # totals. Outside the VAT base, reported here so a manager can reconcile/pay
    # out tips per shift.
    tips: float


class ZReportCash(BaseModel):
    opening_cash: float
    cash_sales: float
    cash_refunds: float
    # FIN-04 / POS-09 drawer movements outside a sale: pay-in adds to the drawer,
    # pay-out (petty cash) and cash-drop (skim to the safe) take from it. The
    # expected cash already folds these in.
    pay_in: float = 0.0
    pay_out: float = 0.0
    cash_drops: float = 0.0
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
    tips_total = 0.0
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
            tips_total += float(t.tip_amount or 0)
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
            "tips": round(tips_total, 2),
        },
        "tenders": tenders,
        "cash": {
            "opening_cash": round(shift.opening_cash or 0, 2),
            "cash_sales": cash_sales,
            "cash_refunds": cash_refunds,
            "pay_in": recon["pay_in"],
            "pay_out": recon["pay_out"],
            "cash_drops": recon["cash_drops"],
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
                        _low_stock_clause(10),
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
    # MA-07: the feature-entitlement tier — the list of feature keys this package
    # unlocks. None ⇒ no tier (package does not restrict features).
    features: Optional[List[str]] = None


class PackageUpdateRequest(BaseModel):
    name: Optional[str] = None
    client_slots: Optional[int] = None
    wholesale_price: Optional[float] = None
    suggested_retail_price: Optional[float] = None
    is_active: Optional[bool] = None
    features: Optional[List[str]] = None


class PackageResponse(BaseModel):
    id: int
    name: str
    client_slots: int
    wholesale_price: float
    suggested_retail_price: Optional[float] = None
    is_active: bool
    # MA-07 feature tier (the enabled keys), parsed from storage. None ⇒ no tier.
    features: Optional[List[str]] = None
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
            features=parse_feature_tier(p.features),
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

    try:
        features_json = normalize_feature_tier(data.features)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    package = Packages(
        name=data.name,
        client_slots=data.client_slots,
        wholesale_price=data.wholesale_price,
        suggested_retail_price=data.suggested_retail_price,
        is_active=data.is_active if data.is_active is not None else True,
        features=features_json,
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
        features=parse_feature_tier(package.features),
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
    # MA-07: a supplied feature tier is validated + serialized for storage.
    if "features" in update_data:
        try:
            update_data["features"] = normalize_feature_tier(update_data["features"])
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
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
        features=parse_feature_tier(package.features),
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