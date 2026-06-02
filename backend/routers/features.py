import csv
import io
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.auth import get_current_user
from schemas.auth import UserResponse
from models.agents import Agents
from models.clients import Clients
from models.products import Products
from models.transactions import Transactions
from models.packages import Packages

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

    return {"role": "master", "entity_id": None, "agent_id": None}


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


@router.post("/api/v1/inventory/deduct", deprecated=True)
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


@router.get("/api/v1/inventory/alerts", response_model=InventoryAlertsResponse)
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

    # Get all transactions in the period
    result = await db.execute(
        select(Transactions).where(
            and_(
                Transactions.client_id == client_id,
                Transactions.created_at >= start_date,
            )
        ).order_by(Transactions.created_at.asc())
    )
    transactions = result.scalars().all()

    # Group by period
    grouped: dict = {}
    for t in transactions:
        if t.created_at is None:
            continue
        if period == "daily":
            key = t.created_at.strftime("%Y-%m-%d")
        elif period == "weekly":
            # ISO week
            key = f"{t.created_at.isocalendar()[0]}-W{t.created_at.isocalendar()[1]:02d}"
        else:  # monthly
            key = t.created_at.strftime("%Y-%m")

        if key not in grouped:
            grouped[key] = {"total": 0.0, "count": 0}
        grouped[key]["total"] += float(t.total_amount or 0)
        grouped[key]["count"] += 1

    items = [
        SalesSummaryItem(
            period=k,
            total_sales=round(v["total"], 2),
            transaction_count=v["count"],
            avg_transaction=round(v["total"] / v["count"], 2) if v["count"] > 0 else 0,
        )
        for k, v in sorted(grouped.items())
    ]

    total_sales = sum(v["total"] for v in grouped.values())
    total_transactions = sum(v["count"] for v in grouped.values())

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

    # Get transactions and parse items_json
    result = await db.execute(
        select(Transactions).where(
            and_(
                Transactions.client_id == client_id,
                Transactions.created_at >= start_date,
            )
        )
    )
    transactions = result.scalars().all()

    # Aggregate product sales
    product_sales: dict = {}
    for t in transactions:
        if not t.items_json:
            continue
        try:
            items = json.loads(t.items_json)
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

    result = await db.execute(
        select(Transactions).where(
            and_(
                Transactions.client_id == client_id,
                Transactions.created_at >= start_date,
            )
        ).order_by(Transactions.created_at.desc())
    )
    transactions = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Invoice Number", "Date", "Subtotal", "VAT", "Discount",
        "Total", "Payment Method", "Status", "Customer Name", "Customer Phone"
    ])

    for t in transactions:
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

    return {"csv_content": output.getvalue(), "row_count": len(transactions)}


# ============================================================
# NOTIFICATIONS (in-memory for simplicity)
# ============================================================

class NotificationItem(BaseModel):
    id: str
    type: str  # "low_stock", "transaction", "system"
    title: str
    message: str
    is_read: bool
    created_at: str


class NotificationsResponse(BaseModel):
    items: List[NotificationItem]
    unread_count: int


@router.get("/api/v1/notifications/list", response_model=NotificationsResponse)
async def get_notifications(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get notifications for current user (generated from low stock and recent transactions)."""
    role_info = await get_user_role(db, str(current_user.id))

    notifications: List[NotificationItem] = []
    now = datetime.now(timezone.utc)

    if role_info["role"] == "client":
        client_id = role_info["entity_id"]

        # Low stock alerts
        result = await db.execute(
            select(Products).where(
                and_(
                    Products.client_id == client_id,
                    Products.quantity < 10,
                    Products.is_active == True,
                )
            ).limit(5)
        )
        low_stock_products = result.scalars().all()

        for p in low_stock_products:
            notifications.append(NotificationItem(
                id=f"low_stock_{p.id}",
                type="low_stock",
                title="Low Stock Alert",
                message=f"{p.name} has only {p.quantity or 0} units remaining",
                is_read=False,
                created_at=now.isoformat(),
            ))

        # Recent transactions (last 5)
        result = await db.execute(
            select(Transactions).where(Transactions.client_id == client_id)
            .order_by(Transactions.created_at.desc())
            .limit(5)
        )
        recent_txns = result.scalars().all()

        for t in recent_txns:
            notifications.append(NotificationItem(
                id=f"txn_{t.id}",
                type="transaction",
                title="Sale Completed",
                message=f"Invoice {t.invoice_number} - {t.total_amount:.2f} SAR",
                is_read=True,
                created_at=t.created_at.isoformat() if t.created_at else now.isoformat(),
            ))

    unread_count = sum(1 for n in notifications if not n.is_read)

    return NotificationsResponse(items=notifications, unread_count=unread_count)


@router.post("/api/v1/notifications/mark-read")
async def mark_notifications_read(
    current_user: UserResponse = Depends(get_current_user),
):
    """Mark all notifications as read (stateless acknowledgment)."""
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