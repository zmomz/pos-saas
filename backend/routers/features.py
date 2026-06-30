import csv
import io
import json
import logging
import os
import secrets
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel
from sqlalchemy import select, func, update, and_, or_, case
from sqlalchemy.ext.asyncio import AsyncSession

from core.cache import invalidate_brand
from core.database import get_db, get_read_db, db_manager
from dependencies.auth import get_current_user
from dependencies.tenancy import get_owner_id
from dependencies.features import require_feature
from services.notifications import NotificationDispatcher
from services.packages import normalize_feature_tier, parse_feature_tier
from services.storage import StorageService
from schemas.storage import FileUpDownRequest
from schemas.auth import UserResponse
from models.auth import User
from models.agents import Agents
from models.clients import Clients
from models.products import Products
from models.categories import Categories
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
    # H7 (ISSUE-038): assign a real category from the merchant's tree.
    category_id: Optional[int] = None
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
    # H7 (ISSUE-038): reassign the linked category.
    category_id: Optional[int] = None
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
    # H7 (ISSUE-038): the linked category id (None when uncategorised).
    category_id: Optional[int] = None
    vat_rate: Optional[float] = None
    is_active: bool
    # POS-11 (F-011): weighted / open-price configuration.
    is_weighted: bool = False
    is_open_price: bool = False
    unit_label: Optional[str] = None
    # ISSUE-065 (P2 catalog): served URL of the product image (None when unset).
    image_url: Optional[str] = None
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


async def _resolve_category_name(
    db: AsyncSession, owner_id: str, category_id: Optional[int]
) -> Optional[str]:
    """H7 (ISSUE-038): validate ``category_id`` belongs to the merchant and return
    its name (denormalised onto the product for display). A non-owned / unknown id
    is rejected with 400 so a product can only be linked to a *real* category."""
    if category_id is None:
        return None
    result = await db.execute(
        select(Categories).where(
            and_(Categories.id == category_id, Categories.user_id == owner_id)
        )
    )
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=400, detail="Category not found")
    return category.name


@router.get("/api/v1/products/list", response_model=ProductListResponse)
async def list_products(
    category: Optional[str] = Query(None),
    category_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    # ISSUE-068 (P2 catalog): archived (soft-deleted) products are hidden from the
    # active catalog / POS by default; the management screen opts in to see them
    # (so they can be restored) by passing ``include_archived=true``.
    include_archived: bool = Query(False),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """List products for current client with optional filters.

    H7 (ISSUE-038): ``category_id`` filters by the linked category tree; the legacy
    free-text ``category`` filter is retained for backward compatibility.

    ISSUE-068: archived products (``is_active=False``) are excluded unless
    ``include_archived`` is set. ``is_distinct_from(False)`` keeps legacy
    NULL-status rows (treated as active) alongside explicitly active ones.
    """
    role_info = await get_user_role(db, owner_id)
    if role_info["role"] != "client":
        raise HTTPException(status_code=403, detail="Only clients can access products")

    client_id = role_info["entity_id"]
    query = select(Products).where(Products.client_id == client_id)

    if not include_archived:
        query = query.where(Products.is_active.is_distinct_from(False))
    if category_id is not None:
        query = query.where(Products.category_id == category_id)
    if category:
        query = query.where(Products.category == category)
    if search:
        query = query.where(Products.name.ilike(f"%{search}%"))

    # Count
    count_query = select(func.count(Products.id)).where(Products.client_id == client_id)
    if not include_archived:
        count_query = count_query.where(Products.is_active.is_distinct_from(False))
    if category_id is not None:
        count_query = count_query.where(Products.category_id == category_id)
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
            category_id=p.category_id,
            vat_rate=p.vat_rate,
            is_active=p.is_active if p.is_active is not None else True,
            is_weighted=bool(p.is_weighted),
            is_open_price=bool(p.is_open_price),
            unit_label=p.unit_label,
            image_url=p.image_url,
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
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Create a new product for the current client."""
    role_info = await get_user_role(db, owner_id)
    if role_info["role"] != "client":
        raise HTTPException(status_code=403, detail="Only clients can create products")

    client_id = role_info["entity_id"]

    # H7 (ISSUE-038): a linked category id wins — its name is denormalised onto the
    # legacy ``category`` string so existing list/display paths keep working.
    linked_name = await _resolve_category_name(db, owner_id, data.category_id)

    product = Products(
        user_id=owner_id,
        client_id=client_id,
        name=data.name,
        name_ar=data.name_ar,
        barcode=data.barcode,
        price=data.price,
        cost_price=data.cost_price,
        quantity=data.quantity or 0,
        reorder_point=data.reorder_point or 0,
        reorder_quantity=data.reorder_quantity or 0,
        category=linked_name if data.category_id is not None else data.category,
        category_id=data.category_id,
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
        category_id=product.category_id,
        vat_rate=product.vat_rate,
        is_active=True,
        is_weighted=bool(product.is_weighted),
        is_open_price=bool(product.is_open_price),
        unit_label=product.unit_label,
        image_url=product.image_url,
        created_at=product.created_at,
        updated_at=product.updated_at,
    )


@router.put("/api/v1/products/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: int,
    data: ProductUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Update a product (client only)."""
    role_info = await get_user_role(db, owner_id)
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
    # H7 (ISSUE-038): reassigning the linked category re-denormalises its name onto
    # the legacy ``category`` string (and validates owner-scoped existence).
    if "category_id" in update_data and update_data["category_id"] is not None:
        update_data["category"] = await _resolve_category_name(
            db, owner_id, update_data["category_id"]
        )
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
        category_id=product.category_id,
        vat_rate=product.vat_rate,
        is_active=product.is_active if product.is_active is not None else True,
        is_weighted=bool(product.is_weighted),
        is_open_price=bool(product.is_open_price),
        unit_label=product.unit_label,
        image_url=product.image_url,
        created_at=product.created_at,
        updated_at=product.updated_at,
    )


# ISSUE-065 (P2 catalog): product image upload. Mirrors the agent-logo pattern
# (AG-01, tenant.py): the file is stored locally under ``uploads/products/`` and
# served from ``/uploads``; the S3-backed object store (routers/storage.py,
# ISSUE-030) remains available for cloud deployments.
_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PRODUCT_IMAGE_DIR = os.path.join(_BACKEND_ROOT, "uploads", "products")
_ALLOWED_IMAGE_TYPES = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
}
_MAX_IMAGE_BYTES = 2 * 1024 * 1024  # 2 MB


@router.post("/api/v1/products/{product_id}/image", response_model=ProductResponse)
async def upload_product_image(
    product_id: int,
    file: UploadFile = File(...),
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Upload an image for one of the client's products (ISSUE-065).

    Validates the declared image type (PNG/JPEG/WebP/GIF) and a 2 MB size cap,
    stores the file under ``uploads/products/``, and persists the served URL on
    the product so the catalog and POS tile grid can render it. Owner-scoped: a
    client can only attach an image to a product they own.
    """
    role_info = await get_user_role(db, owner_id)
    if role_info["role"] != "client":
        raise HTTPException(status_code=403, detail="Only clients can upload product images")

    client_id = role_info["entity_id"]

    result = await db.execute(
        select(Products).where(
            and_(Products.id == product_id, Products.client_id == client_id)
        )
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    ext = _ALLOWED_IMAGE_TYPES.get((file.content_type or "").lower())
    if not ext:
        raise HTTPException(
            status_code=400,
            detail="Unsupported image type. Use PNG, JPEG, WebP, or GIF.",
        )

    contents = await file.read()
    if len(contents) > _MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image exceeds the 2 MB size limit")
    if not contents:
        raise HTTPException(status_code=400, detail="Empty file")

    os.makedirs(_PRODUCT_IMAGE_DIR, exist_ok=True)
    filename = f"product-{product_id}-{secrets.token_hex(6)}.{ext}"
    with open(os.path.join(_PRODUCT_IMAGE_DIR, filename), "wb") as fh:
        fh.write(contents)

    image_url = f"/uploads/products/{filename}"
    await db.execute(
        update(Products)
        .where(and_(Products.id == product_id, Products.client_id == client_id))
        .values(image_url=image_url)
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
        category_id=product.category_id,
        vat_rate=product.vat_rate,
        is_active=product.is_active if product.is_active is not None else True,
        is_weighted=bool(product.is_weighted),
        is_open_price=bool(product.is_open_price),
        unit_label=product.unit_label,
        image_url=product.image_url,
        created_at=product.created_at,
        updated_at=product.updated_at,
    )


@router.delete("/api/v1/products/{product_id}")
async def delete_product(
    product_id: int,
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Deactivate a product (soft delete)."""
    role_info = await get_user_role(db, owner_id)
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


@router.post("/api/v1/products/{product_id}/restore", response_model=ProductResponse)
async def restore_product(
    product_id: int,
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """ISSUE-068 (P2 catalog): un-archive a soft-deleted product.

    Re-activates a product the merchant previously archived via ``DELETE`` so it
    reappears in the active catalog / POS. Owner-scoped — a product the merchant
    does not own is a 404, so one merchant cannot restore another's SKU.
    """
    role_info = await get_user_role(db, owner_id)
    if role_info["role"] != "client":
        raise HTTPException(status_code=403, detail="Only clients can restore products")

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
        .values(is_active=True)
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
        category_id=product.category_id,
        vat_rate=product.vat_rate,
        is_active=True,
        is_weighted=bool(product.is_weighted),
        is_open_price=bool(product.is_open_price),
        unit_label=product.unit_label,
        image_url=product.image_url,
        created_at=product.created_at,
        updated_at=product.updated_at,
    )


@router.get("/api/v1/products/low-stock", response_model=ProductListResponse)
async def get_low_stock_products(
    threshold: int = Query(10, ge=1),
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Get low-stock products.

    INV-08 (F-035): a product is low when on-hand <= its per-product
    ``reorder_point`` (when configured); products without a reorder point fall
    back to the fixed ``threshold`` query param (legacy behaviour).
    """
    role_info = await get_user_role(db, owner_id)
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
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """INV-08 (F-035): auto-PO suggestions for products at/below their reorder point.

    Only products with an explicit ``reorder_point`` (> 0) whose on-hand has
    fallen to or below it are returned — the auto-PO surface is opt-in per
    product. The suggested order quantity is the product's ``reorder_quantity``
    when set, otherwise enough to bring stock back above the reorder point.
    """
    role_info = await get_user_role(db, owner_id)
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
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """DEPRECATED: stock is now deducted atomically inside POST /api/v1/pos/transaction.

    Kept for backward compatibility / manual stock adjustments only. Do not call
    this after creating a transaction or stock will be double-deducted.
    """
    role_info = await get_user_role(db, owner_id)
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
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Get low stock alerts (reorder-point aware; falls back to threshold)."""
    role_info = await get_user_role(db, owner_id)
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

    # M10/#219: capture the domain the brand cache may currently be keyed under, so
    # we can clear the *old* domain key even when this edit changes the domain.
    old_domain = (
        await db.execute(select(Agents.custom_domain).where(Agents.id == agent_id))
    ).scalar_one_or_none()

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
        # M10/#219: clear the agent's cached brand for the by-agent read and for
        # both the old and (possibly new) custom-domain keys.
        new_domain = update_data.get("custom_domain", old_domain)
        await invalidate_brand(agent_id, old_domain, new_domain)

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


# ============================================================
# REPORT → PDF EXPORT (RPT-10, F-072)
# ============================================================
# Every /reports/* endpoint answers ``?format=pdf`` by handing its already
# computed response to a per-report section builder and then to the shared,
# RTL-aware ``services.pdf_render.report_pdf_bytes`` renderer (always-Arabic,
# Latin-1-safe fallback). The reports stay aggregated server-side (OPS-05); the
# PDF is built from the same in-memory response the JSON path returns, so no
# extra query runs.

_FMT_FORMATS = "^(json|pdf)$"


def _m(x) -> str:
    """Money cell: two decimals."""
    return f"{float(x or 0):.2f}"


def _q(x) -> str:
    """Quantity cell: trim trailing zeros."""
    return f"{float(x or 0):g}"


def _ts(value) -> str:
    """Render an ISO timestamp as ``YYYY-MM-DD HH:MM`` (or pass through/blank)."""
    if not value:
        return ""
    return str(value).replace("T", " ")[:16]


def _pdf_response(pdf_bytes: bytes, filename: str) -> Response:
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}.pdf"'},
    )


def _report_pdf(title, meta, sections, filename: str) -> Response:
    """Render the report structure to a PDF download response (F-072)."""
    from services.pdf_render import report_pdf_bytes

    try:
        pdf_bytes = report_pdf_bytes(title=title, meta=meta, sections=sections)
    except RuntimeError as exc:  # fpdf2 missing
        raise HTTPException(status_code=501, detail=str(exc))
    return _pdf_response(pdf_bytes, filename)


def _pdf_sales_summary(resp: "SalesSummaryResponse") -> Response:
    rows = [[i.period, _m(i.total_sales), str(i.transaction_count), _m(i.avg_transaction)] for i in resp.items]
    sections = [{
        "heading": ("المبيعات حسب الفترة", "Sales by period"),
        "columns": [("الفترة", "Period"), ("إجمالي المبيعات", "Total sales"),
                    ("عدد العمليات", "Transactions"), ("متوسط العملية", "Avg sale")],
        "rows": rows,
    }]
    meta = [(("إجمالي المبيعات", "Total sales"), _m(resp.total_sales)),
            (("إجمالي العمليات", "Total transactions"), str(resp.total_transactions))]
    return _report_pdf(("ملخص المبيعات", "Sales Summary"), meta, sections, "sales-summary")


def _pdf_top_products(resp: "TopProductsResponse") -> Response:
    rows = [[i.name, str(i.total_quantity_sold), _m(i.total_revenue)] for i in resp.items]
    sections = [{
        "heading": ("الأكثر مبيعاً", "Top products"),
        "columns": [("الصنف", "Item"), ("الكمية المباعة", "Qty sold"), ("الإيراد", "Revenue")],
        "rows": rows,
        "widths": [110, 35, 35],
    }]
    return _report_pdf(("أفضل المنتجات", "Top Products"), [], sections, "top-products")


def _pdf_payment_breakdown(resp: "PaymentBreakdownResponse") -> Response:
    rows = [[t.tender_type, _m(t.collected), _m(t.refunds), _m(t.net), str(t.count)] for t in resp.tenders]
    sections = [{
        "heading": ("حسب طريقة الدفع", "By payment method"),
        "columns": [("الطريقة", "Method"), ("المحصّل", "Collected"),
                    ("المرتجع", "Refunds"), ("الصافي", "Net"), ("العدد", "Count")],
        "rows": rows,
    }]
    meta = [(("إجمالي المحصّل", "Total collected"), _m(resp.total_collected)),
            (("إجمالي المرتجع", "Total refunds"), _m(resp.total_refunds)),
            (("الصافي", "Net"), _m(resp.net))]
    return _report_pdf(("تفصيل طرق الدفع", "Payment Breakdown"), meta, sections, "payment-breakdown")


def _pdf_journal(resp: "JournalExportResponse") -> Response:
    rows = [[l.account_code, l.account, l.description, _m(l.debit), _m(l.credit)] for l in resp.lines]
    sections = [{
        "heading": ("قيود اليومية", "Journal entries"),
        "columns": [("الرمز", "Code"), ("الحساب", "Account"), ("البيان", "Description"),
                    ("مدين", "Debit"), ("دائن", "Credit")],
        "rows": rows,
        "widths": [20, 45, 65, 30, 30],
    }]
    meta = [(("الفترة", "Period"), f"{resp.from_date}..{resp.to_date}"),
            (("إجمالي المدين", "Total debit"), _m(resp.total_debit)),
            (("إجمالي الدائن", "Total credit"), _m(resp.total_credit)),
            (("متوازن", "Balanced"), "✓" if resp.balanced else "✗")]
    return _report_pdf(("قيد اليومية المحاسبية", "Accounting Journal"), meta, sections, "journal")


def _pdf_profit_margin(resp: "ProfitMarginResponse") -> Response:
    cols = [("الصنف", "Name"), ("الفئة", "Category"), ("الكمية", "Qty"),
            ("الإيراد", "Revenue"), ("التكلفة", "COGS"), ("الربح", "Gross"), ("الهامش %", "Margin %")]

    def _mrows(items):
        return [[r.name, r.category or "", _q(r.qty_sold), _m(r.revenue), _m(r.cogs),
                 _m(r.gross_profit), _m(r.margin_pct)] for r in items]

    sections = [
        {"heading": ("حسب الصنف", "By item"), "columns": cols, "rows": _mrows(resp.by_item)},
        {"heading": ("حسب الفئة", "By category"), "columns": cols, "rows": _mrows(resp.by_category)},
        {"heading": ("المخزون الراكد", "Dead stock"),
         "columns": [("الصنف", "Name"), ("الفئة", "Category"), ("المتوفر", "On hand"),
                     ("التكلفة", "Cost"), ("قيمة المخزون", "Stock value")],
         "rows": [[d.name, d.category or "", _q(d.quantity), _m(d.cost_price), _m(d.stock_value)]
                  for d in resp.dead_stock]},
    ]
    t = resp.totals
    meta = [(("الفترة", "Period"), f"{resp.from_date}..{resp.to_date}"),
            (("الإيراد", "Revenue"), _m(t.revenue)),
            (("التكلفة", "COGS"), _m(t.cogs)),
            (("إجمالي الربح", "Gross profit"), _m(t.gross_profit)),
            (("الهامش %", "Margin %"), _m(t.margin_pct))]
    return _report_pdf(("تقرير الأرباح والهوامش", "Profit & Margin"), meta, sections, "profit-margin")


def _pdf_vat_summary(resp: "VatSummaryResponse") -> Response:
    rows = [[b.label, _q(b.rate), _m(b.taxable_base), _m(b.vat_amount)] for b in resp.buckets]
    sections = [{
        "heading": ("خانات الإقرار الضريبي", "VAT-return boxes"),
        "columns": [("الفئة", "Bucket"), ("النسبة %", "Rate %"),
                    ("الوعاء الخاضع", "Taxable base"), ("الضريبة", "VAT")],
        "rows": rows,
    }]
    meta = [(("الفترة", "Period"), f"{resp.from_date}..{resp.to_date}"),
            (("الضريبة المحصّلة", "VAT collected"), _m(resp.vat_collected)),
            (("الضريبة المرتجعة", "VAT reversed"), _m(resp.vat_reversed)),
            (("صافي الضريبة", "Net VAT"), _m(resp.net_vat)),
            (("إجمالي الوعاء", "Total taxable base"), _m(resp.total_taxable_base))]
    return _report_pdf(("ملخص ضريبة القيمة المضافة", "VAT Summary"), meta, sections, "vat-summary")


def _pdf_inventory(resp: "InventoryReportResponse") -> Response:
    sections = [
        {"heading": ("التقييم حسب الصنف", "Valuation by item"),
         "columns": [("الصنف", "Name"), ("الفئة", "Category"), ("المتوفر", "On hand"),
                     ("التكلفة", "Cost"), ("قيمة المخزون", "Stock value")],
         "rows": [[r.name, r.category or "", _q(r.quantity), _m(r.cost_price), _m(r.stock_value)]
                  for r in resp.by_product]},
        {"heading": ("التقييم حسب الفرع", "Valuation by branch"),
         "columns": [("الفرع", "Branch"), ("المتوفر", "On hand"), ("قيمة المخزون", "Stock value")],
         "rows": [[b.branch_name or f"#{b.branch_id}", _q(b.quantity), _m(b.stock_value)]
                  for b in resp.by_branch]},
        {"heading": ("حركات المخزون", "Stock movements"),
         "columns": [("التاريخ", "Date"), ("النوع", "Type"), ("الصنف", "Product"),
                     ("الكمية", "Qty"), ("المرجع", "Reference")],
         "rows": [[m.date, m.type, m.product_name or (f"#{m.product_id}" if m.product_id else ""),
                   _q(m.quantity), m.reference or ""] for m in resp.movements]},
    ]
    meta = [(("الفترة", "Period"), f"{resp.from_date}..{resp.to_date}"),
            (("إجمالي الكمية", "Total quantity"), _q(resp.total_quantity)),
            (("إجمالي التقييم", "Total valuation"), _m(resp.total_valuation))]
    return _report_pdf(("تقرير المخزون بالتكلفة", "Inventory at Cost"), meta, sections, "inventory")


def _pdf_refunds_voids(resp: "RefundVoidReportResponse") -> Response:
    type_label = {"refund": "مرتجع", "void": "إلغاء"}
    rows = [[type_label.get(r.type, r.type), r.invoice_number or "", r.actor or "",
             r.reason or "", _m(r.amount), _ts(r.timestamp), r.original_invoice or ""] for r in resp.rows]
    sections = [{
        "heading": ("المرتجعات والإلغاءات", "Refunds & voids"),
        "columns": [("النوع", "Type"), ("الفاتورة", "Invoice"), ("المنفّذ", "Actor"),
                    ("السبب", "Reason"), ("المبلغ", "Amount"), ("الوقت", "When"),
                    ("الفاتورة الأصلية", "Original")],
        "rows": rows,
        "widths": [16, 26, 30, 34, 22, 30, 32],
    }]
    meta = [(("الفترة", "Period"), f"{resp.from_date}..{resp.to_date}"),
            (("عدد المرتجعات", "Refund count"), str(resp.refund_count)),
            (("إجمالي المرتجعات", "Refund total"), _m(resp.refund_total)),
            (("عدد الإلغاءات", "Void count"), str(resp.void_count)),
            (("إجمالي الإلغاءات", "Void total"), _m(resp.void_total))]
    return _report_pdf(("المرتجعات والإلغاءات", "Refunds & Voids"), meta, sections, "refunds-voids")


def _pdf_discounts(resp: "DiscountReportResponse") -> Response:
    rows = [[r.invoice_number or "", r.actor or "", (r.code or "يدوي" if r.is_manual else (r.code or "")),
             _m(r.discount_amount), _m(r.subtotal), _ts(r.timestamp)] for r in resp.rows]
    sections = [{
        "heading": ("المبيعات المخصومة", "Discounted sales"),
        "columns": [("الفاتورة", "Invoice"), ("المنفّذ", "Actor"), ("الرمز", "Code"),
                    ("الخصم", "Discount"), ("المجموع الفرعي", "Subtotal"), ("الوقت", "When")],
        "rows": rows,
    }]
    meta = [(("الفترة", "Period"), f"{resp.from_date}..{resp.to_date}"),
            (("عدد الخصومات", "Discount count"), str(resp.discount_count)),
            (("إجمالي الخصومات", "Discount total"), _m(resp.discount_total))]
    return _report_pdf(("تقرير الخصومات", "Discounts"), meta, sections, "discounts")


@router.get("/api/v1/reports/sales-summary", response_model=SalesSummaryResponse)
async def get_sales_summary(
    period: str = Query("daily", pattern="^(daily|weekly|monthly)$"),
    days: int = Query(30, ge=1, le=365),
    format: str = Query("json", pattern=_FMT_FORMATS),
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Get sales summary grouped by period for current client."""
    role_info = await get_user_role(db, owner_id)
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

    resp = SalesSummaryResponse(
        items=items,
        total_sales=round(total_sales, 2),
        total_transactions=total_transactions,
    )
    if format == "pdf":
        return _pdf_sales_summary(resp)
    return resp


@router.get("/api/v1/reports/top-products", response_model=TopProductsResponse)
async def get_top_products(
    limit: int = Query(10, ge=1, le=50),
    days: int = Query(30, ge=1, le=365),
    format: str = Query("json", pattern=_FMT_FORMATS),
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Get top selling products by quantity sold."""
    role_info = await get_user_role(db, owner_id)
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

    resp = TopProductsResponse(items=items)
    if format == "pdf":
        return _pdf_top_products(resp)
    return resp


async def _export_storage_upload_url(object_key: str) -> Optional[str]:
    """Best-effort presigned upload URL for archiving an export to object
    storage — the real caller that keeps StorageService from being a façade
    (ISSUE-030). Returns ``None`` when storage is unconfigured or the gateway is
    unreachable; the export itself never depends on storage being available."""
    if not StorageService.is_configured():
        return None
    try:
        service = StorageService()
        resp = await service.create_upload_url(
            FileUpDownRequest(bucket_name="pos-exports", object_key=object_key)
        )
        return resp.upload_url or None
    except Exception as e:  # storage must never break the export
        logger.warning(f"Export storage upload URL unavailable: {e}")
        return None


@router.get("/api/v1/reports/export-csv")
async def export_transactions_csv(
    days: int = Query(30, ge=1, le=365),
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Export transactions as CSV text."""
    role_info = await get_user_role(db, owner_id)
    if role_info["role"] != "client":
        raise HTTPException(status_code=403, detail="Only clients can export reports")

    client_id = role_info["entity_id"]
    csv_content, row_count = await _build_transactions_csv(db, client_id, days)

    storage_upload_url = await _export_storage_upload_url(f"transactions-{client_id}-{days}d.csv")
    return {
        "csv_content": csv_content,
        "row_count": row_count,
        "storage_upload_url": storage_upload_url,
    }


async def _build_transactions_csv(db: AsyncSession, client_id: str, days: int) -> tuple[str, int]:
    """Render the merchant's transactions CSV for a window — the shared body
    behind both the inline export and the stored-to-object-storage export.

    OPS-05: stream rows through a server-side cursor and write each as we go,
    rather than materializing the whole period into a Python list first.
    """
    start_date = datetime.now(timezone.utc) - timedelta(days=days)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Invoice Number", "Date", "Subtotal", "VAT", "Discount",
        "Total", "Payment Method", "Status", "Customer Name", "Customer Phone"
    ])
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
    return output.getvalue(), row_count


@router.get("/api/v1/reports/export-csv/download")
async def export_transactions_csv_download(
    days: int = Query(30, ge=1, le=365),
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Generate the transactions CSV, store it in object storage, and return a
    presigned download URL so the merchant can retrieve the file (ISSUE-080).

    Unlike the inline ``/export-csv`` endpoint this is a true storage round-trip
    (generate → store → download URL). When object storage is unconfigured it
    degrades to a clear 503 — never an unhandled 500."""
    role_info = await get_user_role(db, owner_id)
    if role_info["role"] != "client":
        raise HTTPException(status_code=403, detail="Only clients can export reports")
    if not StorageService.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Object storage is not configured; export download is unavailable.",
        )

    client_id = role_info["entity_id"]
    csv_content, row_count = await _build_transactions_csv(db, client_id, days)

    # Owner-scoped object key: the client_id is baked into a flat key (the OSS
    # schema sanitizes keys to a basename, so a "/"-prefix would not survive) so
    # one merchant can never collide with or read another's stored export.
    object_key = f"export-{client_id}-transactions-{days}d.csv"
    try:
        stored = await StorageService().store_export(
            FileUpDownRequest(bucket_name="pos-exports", object_key=object_key),
            csv_content.encode("utf-8"),
            content_type="text/csv",
        )
    except ValueError as e:
        logger.error(f"Export storage failed: {e}")
        raise HTTPException(status_code=502, detail="Failed to store export in object storage.")

    return {
        "object_key": object_key,
        "download_url": stored.download_url or None,
        "row_count": row_count,
    }


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
    format: str = Query("json", pattern=_FMT_FORMATS),
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Payment-method breakdown for the period (RPT-03).

    Sales-by-tender and refunds-by-tender from the captured ``payment_tenders``
    rows (F-001/F-004), grouped per method. Card-like legs carry a real approval,
    so the breakdown is what the merchant truly collected per method — not a sum
    of method labels. ``net = collected - refunds``.
    """
    role_info = await get_user_role(db, owner_id)
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

    resp = PaymentBreakdownResponse(
        days=days,
        tenders=tenders,
        total_collected=total_collected,
        total_refunds=total_refunds,
        net=round(total_collected - total_refunds, 2),
    )
    if format == "pdf":
        return _pdf_payment_breakdown(resp)
    return resp


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
    format: str = Query("json", pattern=_FMT_FORMATS),
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Accounting journal / general-ledger export for the period (FIN-02).

    A balanced double-entry journal (sales / VAT / COGS / inventory / payments-by
    -tender) for the trailing ``days`` window. ``Σ debit == Σ credit`` by
    construction; voided and held rows are excluded (neither is realized
    revenue), credit notes net the accounts down via their negative amounts.
    """
    role_info = await get_user_role(db, owner_id)
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

    resp = JournalExportResponse(
        days=days,
        from_date=start_date.date().isoformat(),
        to_date=now.date().isoformat(),
        lines=lines,
        total_debit=total_debit,
        total_credit=total_credit,
        balanced=balanced,
        csv_content=output.getvalue(),
    )
    if format == "pdf":
        return _pdf_journal(resp)
    return resp


# ============================================================
# PROFIT / COGS / MARGIN REPORT + DEAD STOCK (RPT-04 / INV-09, F-068)
# ============================================================
# A merchant can finally see gross profit and margin. COGS is computed
# (moving-average on PO receive) but until now only surfaced inside the GL
# journal. This report breaks revenue / COGS / gross profit / margin % down by
# item and by category over a trailing window, and lists dead stock (no sale in
# N days, on-hand > 0) so slow movers can be marked down or returned.
#
# Margin is stable over time because each sale line snapshots its product cost
# at sale time (F-068, services/sale_core.snapshot_cost_prices): the report reads
# that snapshot in preference to the live cost, so a later cost change does not
# rewrite history. Legacy lines with no snapshot fall back to the current cost.
#
# Aggregated server-side (OPS-05, never load-everything): the catalog cost map is
# bounded, and each transaction's items_json is streamed exactly once.

class MarginRow(BaseModel):
    key: str
    name: str
    category: Optional[str] = None
    qty_sold: float
    revenue: float
    cogs: float
    gross_profit: float
    margin_pct: float


class DeadStockRow(BaseModel):
    product_id: int
    name: str
    category: Optional[str] = None
    quantity: float
    cost_price: float
    stock_value: float


class ProfitMarginResponse(BaseModel):
    days: int
    from_date: str
    to_date: str
    dead_stock_days: int
    by_item: List[MarginRow]
    by_category: List[MarginRow]
    dead_stock: List[DeadStockRow]
    totals: MarginRow
    csv_content: str


def _margin_pct(revenue: float, gross: float) -> float:
    """Gross margin as a % of revenue (0 when there is no revenue)."""
    return round((gross / revenue) * 100, 2) if revenue else 0.0


@router.get("/api/v1/reports/profit-margin", response_model=ProfitMarginResponse)
async def report_profit_margin(
    days: int = Query(30, ge=1, le=365),
    dead_stock_days: int = Query(30, ge=1, le=365),
    format: str = Query("json", pattern=_FMT_FORMATS),
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Profit / COGS / margin by item and category, plus a dead-stock list (F-068).

    Revenue and COGS are netted by credit notes (refunds reverse both). COGS uses
    the per-line cost snapshot taken at sale time, falling back to the live product
    cost for legacy lines. Owner-scoped to the calling client (SEC-02), windowed by
    ``days``; dead stock is products with on-hand > 0 and no sale in
    ``dead_stock_days``. Aggregated by streaming items_json once (OPS-05).
    """
    role_info = await get_user_role(db, owner_id)
    if role_info["role"] != "client":
        raise HTTPException(status_code=403, detail="Only clients can view the profit/margin report")

    client_id = role_info["entity_id"]
    now = datetime.now(timezone.utc)
    start_date = now - timedelta(days=days)

    # ---- Bounded product catalog (id -> name / category / cost / on-hand) ----
    prod_rows = (
        await db.execute(
            select(
                Products.id,
                Products.name,
                Products.category,
                Products.cost_price,
                Products.quantity,
            ).where(Products.client_id == client_id)
        )
    ).all()
    catalog = {r[0]: r for r in prod_rows}
    cost_map = {r[0]: float(r[3] or 0.0) for r in prod_rows}

    not_excluded = and_(
        Transactions.status.is_distinct_from("held"),
        Transactions.status.is_distinct_from("voided"),
    )

    # ---- Stream items_json once, aggregating revenue/COGS/qty per product ----
    per_product: dict = {}
    sold_pids: set = set()
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
        # A credit note (refund) reverses both revenue and COGS.
        sign = -1.0 if status == "credit_note" else 1.0
        for item in items:
            pid = item.get("product_id")
            qty = float(item.get("quantity", 0) or 0)
            price = float(item.get("price", 0) or 0)
            line_disc = float(item.get("discount", 0) or 0)
            # The sale-time snapshot wins; legacy lines fall back to current cost.
            snap = item.get("cost_price")
            cost = float(snap) if snap is not None else cost_map.get(pid, 0.0)
            if pid is not None:
                sold_pids.add(pid)
            agg = per_product.setdefault(
                pid, {"qty": 0.0, "revenue": 0.0, "cogs": 0.0}
            )
            agg["qty"] += sign * qty
            agg["revenue"] += sign * (price * qty - line_disc)
            agg["cogs"] += sign * cost * qty

    # ---- Per-item rows (largest gross profit first) ----
    by_item: List[MarginRow] = []
    by_category_agg: dict = {}
    tot_qty = tot_rev = tot_cogs = 0.0
    for pid, agg in per_product.items():
        revenue = round(agg["revenue"], 2)
        cogs = round(agg["cogs"], 2)
        gross = round(revenue - cogs, 2)
        prod = catalog.get(pid)
        name = prod[1] if prod else (f"Item #{pid}" if pid is not None else "Ad-hoc")
        category = (prod[2] if prod else None) or None
        by_item.append(
            MarginRow(
                key=str(pid) if pid is not None else "adhoc",
                name=name,
                category=category,
                qty_sold=round(agg["qty"], 3),
                revenue=revenue,
                cogs=cogs,
                gross_profit=gross,
                margin_pct=_margin_pct(revenue, gross),
            )
        )
        cat_key = category or "Uncategorized"
        cat = by_category_agg.setdefault(
            cat_key, {"qty": 0.0, "revenue": 0.0, "cogs": 0.0}
        )
        cat["qty"] += agg["qty"]
        cat["revenue"] += agg["revenue"]
        cat["cogs"] += agg["cogs"]
        tot_qty += agg["qty"]
        tot_rev += agg["revenue"]
        tot_cogs += agg["cogs"]
    by_item.sort(key=lambda r: (-r.gross_profit, r.name))

    # ---- Per-category rows ----
    by_category: List[MarginRow] = []
    for cat_key, agg in by_category_agg.items():
        revenue = round(agg["revenue"], 2)
        cogs = round(agg["cogs"], 2)
        gross = round(revenue - cogs, 2)
        by_category.append(
            MarginRow(
                key=cat_key,
                name=cat_key,
                category=cat_key,
                qty_sold=round(agg["qty"], 3),
                revenue=revenue,
                cogs=cogs,
                gross_profit=gross,
                margin_pct=_margin_pct(revenue, gross),
            )
        )
    by_category.sort(key=lambda r: (-r.gross_profit, r.name))

    tot_rev = round(tot_rev, 2)
    tot_cogs = round(tot_cogs, 2)
    tot_gross = round(tot_rev - tot_cogs, 2)
    totals = MarginRow(
        key="__total__",
        name="Total",
        category=None,
        qty_sold=round(tot_qty, 3),
        revenue=tot_rev,
        cogs=tot_cogs,
        gross_profit=tot_gross,
        margin_pct=_margin_pct(tot_rev, tot_gross),
    )

    # ---- Dead stock (on-hand > 0, no sale in dead_stock_days) ----
    # Reuse the report window's sold set when the windows match; otherwise stream
    # the dead-stock window once collecting only the sold product ids (bounded).
    if dead_stock_days == days:
        sold_recent = sold_pids
    else:
        sold_recent = set()
        ds_start = now - timedelta(days=dead_stock_days)
        ds_stream = await db.stream(
            select(Transactions.items_json).where(
                and_(
                    Transactions.client_id == client_id,
                    Transactions.created_at >= ds_start,
                    not_excluded,
                )
            )
        )
        async for (items_json,) in ds_stream:
            if not items_json:
                continue
            try:
                for item in json.loads(items_json):
                    if item.get("product_id") is not None:
                        sold_recent.add(item.get("product_id"))
            except (json.JSONDecodeError, TypeError):
                continue

    dead_stock: List[DeadStockRow] = []
    for pid, prod in catalog.items():
        on_hand = float(prod[4] or 0.0)
        if on_hand > 0 and pid not in sold_recent:
            cost = float(prod[3] or 0.0)
            dead_stock.append(
                DeadStockRow(
                    product_id=pid,
                    name=prod[1],
                    category=prod[2] or None,
                    quantity=round(on_hand, 3),
                    cost_price=round(cost, 2),
                    stock_value=round(on_hand * cost, 2),
                )
            )
    dead_stock.sort(key=lambda r: (-r.stock_value, r.name))

    # ---- CSV (per-item margin + a dead-stock section) ----
    output = io.StringIO()
    writer = csv.writer(output)
    period_label = f"{start_date.date().isoformat()}..{now.date().isoformat()}"
    writer.writerow(
        ["Type", "Key", "Name", "Category", "Qty Sold", "Revenue", "COGS", "Gross Profit", "Margin %"]
    )
    for r in by_item:
        writer.writerow(
            ["ITEM", r.key, r.name, r.category or "", f"{r.qty_sold:g}",
             f"{r.revenue:.2f}", f"{r.cogs:.2f}", f"{r.gross_profit:.2f}", f"{r.margin_pct:.2f}"]
        )
    for r in by_category:
        writer.writerow(
            ["CATEGORY", r.key, r.name, "", f"{r.qty_sold:g}",
             f"{r.revenue:.2f}", f"{r.cogs:.2f}", f"{r.gross_profit:.2f}", f"{r.margin_pct:.2f}"]
        )
    writer.writerow(
        ["TOTAL", "", "Total", "", f"{totals.qty_sold:g}",
         f"{totals.revenue:.2f}", f"{totals.cogs:.2f}", f"{totals.gross_profit:.2f}", f"{totals.margin_pct:.2f}"]
    )
    writer.writerow([])
    writer.writerow(["Dead stock (no sale in last %d days)" % dead_stock_days])
    writer.writerow(["Product ID", "Name", "Category", "On Hand", "Cost", "Stock Value"])
    for d in dead_stock:
        writer.writerow(
            [d.product_id, d.name, d.category or "", f"{d.quantity:g}",
             f"{d.cost_price:.2f}", f"{d.stock_value:.2f}"]
        )

    resp = ProfitMarginResponse(
        days=days,
        from_date=start_date.date().isoformat(),
        to_date=now.date().isoformat(),
        dead_stock_days=dead_stock_days,
        by_item=by_item,
        by_category=by_category,
        dead_stock=dead_stock,
        totals=totals,
        csv_content=output.getvalue(),
    )
    if format == "pdf":
        return _pdf_profit_margin(resp)
    return resp


# ============================================================
# VAT / TAX SUMMARY BY RATE (RPT-05, F-069)
# ============================================================
# A merchant filing a ZATCA VAT return needs output VAT broken out by rate, not
# the single aggregate ``vat_amount`` line the journal carries. This report
# aggregates the window's sales into the ZATCA VAT-return boxes —
# **standard-rated (15%) / zero-rated (0%) / exempt** — each with its **taxable
# base** and **VAT amount**.
#
# VAT is charged once per sale at a single rate (the global rate, MA-05, or the
# per-request fallback), and a credit note (refund) is stored with **negative**
# subtotal/VAT (POS-07), so a plain signed SUM nets collected − reversed for free.
# Each sale is bucketed by the VAT it actually carried: any VAT > 0 is the
# standard-rated box, VAT == 0 is zero-rated. The data model carries no exempt
# tax-category marker yet, so the **exempt** box is always emitted (ZATCA-return
# parity) but stays empty until exempt supplies are modelled.
#
# Aggregated entirely in SQL (OPS-05, never load-everything): a single grouped
# query over the date-windowed, owner-scoped transactions.

class VatBucket(BaseModel):
    key: str            # "standard" | "zero" | "exempt"
    label: str
    rate: float
    taxable_base: float
    vat_amount: float   # net of credit notes (collected − reversed) in this box


class VatSummaryResponse(BaseModel):
    days: int
    from_date: str
    to_date: str
    buckets: List[VatBucket]
    total_taxable_base: float
    vat_collected: float
    vat_reversed: float
    net_vat: float
    csv_content: str


@router.get("/api/v1/reports/vat-summary", response_model=VatSummaryResponse)
async def report_vat_summary(
    days: int = Query(30, ge=1, le=365),
    format: str = Query("json", pattern=_FMT_FORMATS),
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Output VAT by rate over a window — the ZATCA VAT-return boxes (F-069).

    Buckets the window's sales into standard-rated (15%) / zero-rated (0%) / exempt,
    each with taxable base and VAT. Credit notes carry negative amounts so a signed
    SUM nets collected − reversed. Owner-scoped to the calling client (SEC-02),
    windowed by ``days``, aggregated in SQL (OPS-05).
    """
    role_info = await get_user_role(db, owner_id)
    if role_info["role"] != "client":
        raise HTTPException(status_code=403, detail="Only clients can view the VAT summary report")

    client_id = role_info["entity_id"]
    now = datetime.now(timezone.utc)
    start_date = now - timedelta(days=days)

    # Held tickets / voided sales are not fiscal supplies; everything else
    # (completed sales + credit notes) nets via signed amounts. ``is_distinct_from``
    # keeps NULL-status legacy completed sales in.
    not_excluded = and_(
        Transactions.status.is_distinct_from("held"),
        Transactions.status.is_distinct_from("voided"),
    )
    base_expr = func.coalesce(Transactions.subtotal, 0.0) - func.coalesce(
        Transactions.discount_amount, 0.0
    )
    vat_expr = func.coalesce(Transactions.vat_amount, 0.0)
    # Standard-rated when any VAT was charged; otherwise zero-rated. A credit note's
    # VAT is negative, so ``abs`` keeps a 15% refund in the standard box where it
    # nets the collected total down.
    bucket_expr = case((func.abs(vat_expr) > 0.005, "standard"), else_="zero")

    rows = (
        await db.execute(
            select(
                bucket_expr.label("bucket"),
                func.sum(base_expr),
                func.sum(vat_expr),
                func.sum(case((vat_expr > 0, vat_expr), else_=0.0)),
                func.sum(case((vat_expr < 0, -vat_expr), else_=0.0)),
            )
            .where(
                and_(
                    Transactions.client_id == client_id,
                    Transactions.created_at >= start_date,
                    not_excluded,
                )
            )
            .group_by(bucket_expr)
        )
    ).all()

    agg = {r[0]: r for r in rows}

    def _box(key: str, label: str, rate: float) -> VatBucket:
        r = agg.get(key)
        return VatBucket(
            key=key,
            label=label,
            rate=rate,
            taxable_base=round(float(r[1] or 0.0), 2) if r else 0.0,
            vat_amount=round(float(r[2] or 0.0), 2) if r else 0.0,
        )

    buckets = [
        _box("standard", "Standard-rated (15%)", 15.0),
        _box("zero", "Zero-rated (0%)", 0.0),
        # No exempt tax-category marker in the model yet — always-present, empty box.
        VatBucket(key="exempt", label="Exempt", rate=0.0, taxable_base=0.0, vat_amount=0.0),
    ]

    vat_collected = round(sum(float(r[3] or 0.0) for r in rows), 2)
    vat_reversed = round(sum(float(r[4] or 0.0) for r in rows), 2)
    net_vat = round(vat_collected - vat_reversed, 2)
    total_taxable_base = round(sum(b.taxable_base for b in buckets), 2)

    # ---- CSV (one row per ZATCA box + the collected/reversed/net summary) ----
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["VAT Bucket", "Rate %", "Taxable Base", "VAT Amount"])
    for b in buckets:
        writer.writerow([b.label, f"{b.rate:g}", f"{b.taxable_base:.2f}", f"{b.vat_amount:.2f}"])
    writer.writerow([])
    writer.writerow(["VAT collected", f"{vat_collected:.2f}"])
    writer.writerow(["VAT reversed (credit notes)", f"{vat_reversed:.2f}"])
    writer.writerow(["Net VAT payable", f"{net_vat:.2f}"])
    writer.writerow(["Total taxable base", f"{total_taxable_base:.2f}"])

    resp = VatSummaryResponse(
        days=days,
        from_date=start_date.date().isoformat(),
        to_date=now.date().isoformat(),
        buckets=buckets,
        total_taxable_base=total_taxable_base,
        vat_collected=vat_collected,
        vat_reversed=vat_reversed,
        net_vat=net_vat,
        csv_content=output.getvalue(),
    )
    if format == "pdf":
        return _pdf_vat_summary(resp)
    return resp


# ============================================================
# INVENTORY REPORT — on-hand valuation at cost + movements (RPT-07, F-070)
# ============================================================
# A merchant could not pull a stock valuation at cost or a movement ledger: the
# only stock figure was a dashboard stat valued at SALE price (production.py —
# now corrected to cost). This report gives the two things every POS leader
# (Rewaa, Marn, Foodics) surfaces:
#
#   • On-hand valuation at ``cost_price`` — the money tied up in inventory, per
#     product (the authoritative client-level on-hand) and per branch (the
#     per-branch ledger the POS deducts from), with a grand total.
#   • A movement ledger over a trailing window — PO receipts (INV-07), inter-branch
#     transfers (INV-05) and counts/adjustments (INV-06) — so stock changes are
#     traceable.
#
# Owner-scoped to the calling client (SEC-02). Valuation reads a bounded catalog;
# the movement tables are naturally small and windowed (OPS-05, no load-everything
# items_json stream is needed here).

class InventoryValuationRow(BaseModel):
    product_id: int
    name: str
    category: Optional[str] = None
    quantity: float
    cost_price: float
    stock_value: float


class BranchValuationRow(BaseModel):
    branch_id: int
    branch_name: Optional[str] = None
    quantity: float
    stock_value: float


class InventoryMovementRow(BaseModel):
    date: str
    type: str  # "receipt" | "transfer" | "adjustment"
    product_id: Optional[int] = None
    product_name: Optional[str] = None
    quantity: float       # signed change (receipts +, adjustments = variance, …)
    reference: Optional[str] = None
    note: Optional[str] = None


class InventoryReportResponse(BaseModel):
    days: int
    from_date: str
    to_date: str
    by_product: List[InventoryValuationRow]
    by_branch: List[BranchValuationRow]
    total_quantity: float
    total_valuation: float
    movements: List[InventoryMovementRow]
    csv_content: str


@router.get("/api/v1/reports/inventory", response_model=InventoryReportResponse)
async def report_inventory(
    days: int = Query(30, ge=1, le=365),
    format: str = Query("json", pattern=_FMT_FORMATS),
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """On-hand inventory valued at ``cost_price`` + a movement ledger (F-070).

    Valuation is at cost (never sale price) per product and per branch, with a
    grand total. The movement feed pulls PO receipts, inter-branch transfers and
    counts/adjustments over the trailing ``days`` window. Owner-scoped to the
    calling client (SEC-02). Aggregated in SQL over bounded/windowed tables
    (OPS-05).
    """
    from models.branches import Branches
    from models.product_branch_stock import Product_branch_stock
    from models.purchase_orders import Purchase_orders
    from models.stock_adjustments import Stock_adjustments
    from models.stock_transfers import Stock_transfers

    role_info = await get_user_role(db, owner_id)
    if role_info["role"] != "client":
        raise HTTPException(status_code=403, detail="Only clients can view the inventory report")

    client_id = role_info["entity_id"]
    user_id = owner_id
    now = datetime.now(timezone.utc)
    start_date = now - timedelta(days=days)

    # ---- On-hand valuation at cost, per product (bounded catalog) ----
    prod_rows = (
        await db.execute(
            select(
                Products.id,
                Products.name,
                Products.category,
                Products.cost_price,
                Products.quantity,
            ).where(
                and_(Products.client_id == client_id, Products.is_active == True)  # noqa: E712
            )
        )
    ).all()

    by_product: List[InventoryValuationRow] = []
    total_qty = 0.0
    total_value = 0.0
    for pid, name, category, cost_price, quantity in prod_rows:
        qty = float(quantity or 0.0)
        cost = float(cost_price or 0.0)
        value = round(qty * cost, 2)
        total_qty += qty
        total_value += value
        by_product.append(
            InventoryValuationRow(
                product_id=pid,
                name=name,
                category=category or None,
                quantity=round(qty, 3),
                cost_price=round(cost, 2),
                stock_value=value,
            )
        )
    by_product.sort(key=lambda r: (-r.stock_value, r.name))
    total_qty = round(total_qty, 3)
    total_value = round(total_value, 2)

    # ---- Per-branch valuation at cost (the ledger the POS deducts from) ----
    # SUM(on-hand × cost) grouped by branch, in SQL (OPS-05). Joins the product's
    # cost onto each ledger row; only branches with explicit ledger rows appear
    # (a branch with no allocation is represented in the client-level product
    # aggregate above).
    branch_qty_expr = func.coalesce(Product_branch_stock.quantity, 0.0)
    branch_value_rows = (
        await db.execute(
            select(
                Product_branch_stock.branch_id,
                func.sum(branch_qty_expr * func.coalesce(Products.cost_price, 0.0)),
                func.sum(branch_qty_expr),
            )
            .join(Products, Products.id == Product_branch_stock.product_id)
            .where(Product_branch_stock.client_id == client_id)
            .group_by(Product_branch_stock.branch_id)
        )
    ).all()

    branch_names = {
        b.id: b.name
        for b in (
            await db.execute(select(Branches).where(Branches.user_id == user_id))
        ).scalars().all()
    }
    by_branch: List[BranchValuationRow] = [
        BranchValuationRow(
            branch_id=bid,
            branch_name=branch_names.get(bid),
            quantity=round(float(qty or 0.0), 3),
            stock_value=round(float(value or 0.0), 2),
        )
        for bid, value, qty in branch_value_rows
    ]
    by_branch.sort(key=lambda r: (-r.stock_value, r.branch_id))

    # ---- Movement ledger over the window (owner-scoped, windowed) ----
    movements: List[InventoryMovementRow] = []

    # PO receipts (INV-07): a received / partially-received PO over the window;
    # each received product line is one receipt movement.
    po_rows = (
        await db.execute(
            select(Purchase_orders).where(
                and_(
                    Purchase_orders.user_id == user_id,
                    Purchase_orders.status.in_(["received", "partially_received"]),
                    Purchase_orders.updated_at >= start_date,
                )
            )
        )
    ).scalars().all()
    for po in po_rows:
        try:
            lines = json.loads(po.items_json) if po.items_json else []
        except (json.JSONDecodeError, TypeError):
            lines = []
        po_date = po.received_date or (
            po.updated_at.date().isoformat() if po.updated_at else now.date().isoformat()
        )
        for line in lines if isinstance(lines, list) else []:
            received = float(line.get("received") or 0)
            if received <= 0:
                continue
            movements.append(
                InventoryMovementRow(
                    date=po_date,
                    type="receipt",
                    product_id=line.get("product_id"),
                    product_name=line.get("product_name") or line.get("name"),
                    quantity=round(received, 3),
                    reference=po.order_number or f"PO #{po.id}",
                    note=None,
                )
            )

    # Inter-branch transfers (INV-05).
    transfer_rows = (
        await db.execute(
            select(Stock_transfers).where(
                and_(
                    Stock_transfers.user_id == user_id,
                    Stock_transfers.created_at >= start_date,
                )
            )
        )
    ).scalars().all()
    for t in transfer_rows:
        src = branch_names.get(t.from_branch_id, f"#{t.from_branch_id}")
        dst = branch_names.get(t.to_branch_id, f"#{t.to_branch_id}")
        movements.append(
            InventoryMovementRow(
                date=t.created_at.date().isoformat() if t.created_at else now.date().isoformat(),
                type="transfer",
                product_id=t.product_id,
                product_name=t.product_name,
                quantity=round(float(t.quantity or 0), 3),
                reference=f"{src} → {dst}",
                note=None,
            )
        )

    # Counts / adjustments (INV-06): the signed variance is the movement.
    adj_rows = (
        await db.execute(
            select(Stock_adjustments).where(
                and_(
                    Stock_adjustments.user_id == user_id,
                    Stock_adjustments.created_at >= start_date,
                )
            )
        )
    ).scalars().all()
    for a in adj_rows:
        movements.append(
            InventoryMovementRow(
                date=a.created_at.date().isoformat() if a.created_at else now.date().isoformat(),
                type="adjustment",
                product_id=a.product_id,
                product_name=a.product_name,
                quantity=round(float(a.variance or 0), 3),
                reference=a.reason,
                note=a.note,
            )
        )

    # Newest first; stable on (date, type) so a window reads like a ledger.
    movements.sort(key=lambda m: (m.date, m.type), reverse=True)

    # ---- CSV (valuation rows + a movement section) ----
    output = io.StringIO()
    writer = csv.writer(output)
    period_label = f"{start_date.date().isoformat()}..{now.date().isoformat()}"
    writer.writerow(["Inventory valuation at cost", period_label])
    writer.writerow(["Product ID", "Name", "Category", "On Hand", "Cost", "Stock Value"])
    for r in by_product:
        writer.writerow(
            [r.product_id, r.name, r.category or "", f"{r.quantity:g}",
             f"{r.cost_price:.2f}", f"{r.stock_value:.2f}"]
        )
    writer.writerow(["", "", "TOTAL", f"{total_qty:g}", "", f"{total_value:.2f}"])
    writer.writerow([])
    writer.writerow(["Per-branch valuation at cost"])
    writer.writerow(["Branch ID", "Branch", "On Hand", "Stock Value"])
    for b in by_branch:
        writer.writerow(
            [b.branch_id, b.branch_name or "", f"{b.quantity:g}", f"{b.stock_value:.2f}"]
        )
    writer.writerow([])
    writer.writerow(["Stock movements (last %d days)" % days])
    writer.writerow(["Date", "Type", "Product", "Quantity", "Reference", "Note"])
    for m in movements:
        writer.writerow(
            [m.date, m.type, m.product_name or (f"#{m.product_id}" if m.product_id else ""),
             f"{m.quantity:g}", m.reference or "", m.note or ""]
        )

    resp = InventoryReportResponse(
        days=days,
        from_date=start_date.date().isoformat(),
        to_date=now.date().isoformat(),
        by_product=by_product,
        by_branch=by_branch,
        total_quantity=total_qty,
        total_valuation=total_value,
        movements=movements,
        csv_content=output.getvalue(),
    )
    if format == "pdf":
        return _pdf_inventory(resp)
    return resp


# ============================================================
# REFUND / VOID + DISCOUNT REPORTS (RPT-08, F-071)
# ============================================================
# A manager could only audit refunds/voids/discounts per-shift inside the Z-report
# (_aggregate_zreport buckets them by transaction status). These two reports
# generalize that same bucketing across a date window and add the audit dimension
# the Z-report omits — WHO did it, WHY, and WHEN — by joining the POS_VOID_SALE
# audit event (POS-08) and the credit-note / sale rows.
#
#   • /reports/refunds-voids — every refund (credit note) and void in the window,
#     each with actor, reason, amount, timestamp. A void draws actor/reason/when
#     from its audit row; a refund from the credit-note transaction.
#   • /reports/discounts — every discounted sale in the window with actor, the
#     applied code (or a manual flag for a codeless override), amount, timestamp.
#
# Owner-scoped to the calling client (SEC-02), windowed by ``days``. Aggregated in
# SQL over windowed tables (OPS-05); actor names resolved in one bounded lookup.


def _void_reason_from_details(details: Optional[str]) -> Optional[str]:
    """Pull the cashier reason out of a POS_VOID_SALE audit detail string.

    The void handler (routers/pos.py) writes ``… — reason: <reason>`` when a reason
    was given; return that tail, else None.
    """
    if not details:
        return None
    marker = "reason:"
    idx = details.find(marker)
    if idx == -1:
        return None
    reason = details[idx + len(marker):].strip()
    return reason or None


async def _resolve_actor_names(db: AsyncSession, user_ids) -> dict:
    """Map user ids → a display name (name, else email, else the raw id).

    One bounded ``IN`` lookup over the users table so each report row can name who
    performed the action without an N+1 query.
    """
    ids = {str(u) for u in user_ids if u}
    if not ids:
        return {}
    rows = (
        await db.execute(select(User.id, User.name, User.email).where(User.id.in_(ids)))
    ).all()
    return {r[0]: (r[1] or r[2] or r[0]) for r in rows}


class RefundVoidRow(BaseModel):
    type: str  # "refund" | "void"
    transaction_id: int
    invoice_number: Optional[str] = None
    actor_id: Optional[str] = None
    actor: Optional[str] = None
    reason: Optional[str] = None
    amount: float                       # positive amount reversed / voided
    timestamp: Optional[str] = None
    original_invoice: Optional[str] = None  # the sale a refund reverses


class RefundVoidReportResponse(BaseModel):
    days: int
    from_date: str
    to_date: str
    rows: List[RefundVoidRow]
    refund_count: int
    refund_total: float
    void_count: int
    void_total: float
    csv_content: str


@router.get("/api/v1/reports/refunds-voids", response_model=RefundVoidReportResponse)
async def report_refunds_voids(
    days: int = Query(30, ge=1, le=365),
    format: str = Query("json", pattern=_FMT_FORMATS),
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Every refund + void over a window with actor / reason / amount / time (F-071).

    Refunds are the credit-note transactions (POS-07; the negative amounts reported
    as the positive amount reversed). Voids are the POS_VOID_SALE audit events
    (POS-08) — the actor, reason and timestamp come from the audit row, the amount
    from the voided sale. Owner-scoped to the calling client (SEC-02), windowed by
    ``days``.
    """
    from models.audit_logs import Audit_logs

    role_info = await get_user_role(db, owner_id)
    if role_info["role"] != "client":
        raise HTTPException(status_code=403, detail="Only clients can view the refunds/voids report")

    client_id = role_info["entity_id"]
    now = datetime.now(timezone.utc)
    start_date = now - timedelta(days=days)

    rows: List[RefundVoidRow] = []

    # ---- Refunds: credit-note transactions in the window (POS-07) ----
    cn_rows = (
        await db.execute(
            select(Transactions).where(
                and_(
                    Transactions.client_id == client_id,
                    Transactions.status == "credit_note",
                    Transactions.created_at >= start_date,
                )
            )
        )
    ).scalars().all()

    # Resolve each credit note's original invoice number (bounded lookup).
    orig_ids = {cn.original_transaction_id for cn in cn_rows if cn.original_transaction_id}
    orig_invoice: dict = {}
    if orig_ids:
        orig_invoice = {
            r[0]: r[1]
            for r in (
                await db.execute(
                    select(Transactions.id, Transactions.invoice_number).where(
                        Transactions.id.in_(orig_ids)
                    )
                )
            ).all()
        }

    refund_total = 0.0
    for cn in cn_rows:
        amount = round(abs(float(cn.total_amount or 0)), 2)
        refund_total += amount
        rows.append(
            RefundVoidRow(
                type="refund",
                transaction_id=cn.id,
                invoice_number=cn.invoice_number,
                actor_id=cn.user_id,
                reason=None,  # credit notes carry no captured reason
                amount=amount,
                timestamp=cn.created_at.isoformat() if cn.created_at else None,
                original_invoice=orig_invoice.get(cn.original_transaction_id),
            )
        )
    refund_count = len(cn_rows)

    # ---- Voids: the POS_VOID_SALE audit events in the window (POS-08) ----
    # The void event (actor / reason / when) lives in audit_logs; the amount on the
    # voided transaction. Owner-scoped by intersecting with this client's txns.
    void_audits = (
        await db.execute(
            select(Audit_logs).where(
                and_(
                    Audit_logs.action == "POS_VOID_SALE",
                    Audit_logs.created_at >= start_date,
                )
            )
        )
    ).scalars().all()

    void_txn_ids: set = set()
    for a in void_audits:
        try:
            void_txn_ids.add(int(a.entity_id))
        except (TypeError, ValueError):
            continue
    void_txn: dict = {}
    if void_txn_ids:
        void_txn = {
            t.id: t
            for t in (
                await db.execute(
                    select(Transactions).where(
                        and_(
                            Transactions.id.in_(void_txn_ids),
                            Transactions.client_id == client_id,
                        )
                    )
                )
            ).scalars().all()
        }

    void_total = 0.0
    void_count = 0
    for a in void_audits:
        try:
            tid = int(a.entity_id)
        except (TypeError, ValueError):
            continue
        txn = void_txn.get(tid)
        if txn is None:
            continue  # not this client's sale (SEC-02) — skip
        amount = round(abs(float(txn.total_amount or 0)), 2)
        void_total += amount
        void_count += 1
        rows.append(
            RefundVoidRow(
                type="void",
                transaction_id=txn.id,
                invoice_number=txn.invoice_number,
                actor_id=a.user_id,
                reason=_void_reason_from_details(a.details),
                amount=amount,
                timestamp=a.created_at.isoformat() if a.created_at else None,
                original_invoice=None,
            )
        )

    # Resolve actor display names in one bounded lookup, then stamp each row.
    name_map = await _resolve_actor_names(db, [r.actor_id for r in rows])
    for r in rows:
        r.actor = name_map.get(r.actor_id or "", r.actor_id)

    # Newest first across both kinds (ISO timestamps sort lexicographically).
    rows.sort(key=lambda r: (r.timestamp or ""), reverse=True)

    refund_total = round(refund_total, 2)
    void_total = round(void_total, 2)

    # ---- CSV ----
    output = io.StringIO()
    writer = csv.writer(output)
    period_label = f"{start_date.date().isoformat()}..{now.date().isoformat()}"
    writer.writerow(["Refunds & voids", period_label])
    writer.writerow(
        ["Type", "Invoice", "Actor", "Reason", "Amount", "Timestamp", "Original Invoice"]
    )
    for r in rows:
        writer.writerow(
            [r.type, r.invoice_number or "", r.actor or "", r.reason or "",
             f"{r.amount:.2f}", r.timestamp or "", r.original_invoice or ""]
        )
    writer.writerow([])
    writer.writerow(["Refund count", refund_count, "Refund total", f"{refund_total:.2f}"])
    writer.writerow(["Void count", void_count, "Void total", f"{void_total:.2f}"])

    resp = RefundVoidReportResponse(
        days=days,
        from_date=start_date.date().isoformat(),
        to_date=now.date().isoformat(),
        rows=rows,
        refund_count=refund_count,
        refund_total=refund_total,
        void_count=void_count,
        void_total=void_total,
        csv_content=output.getvalue(),
    )
    if format == "pdf":
        return _pdf_refunds_voids(resp)
    return resp


class DiscountRow(BaseModel):
    transaction_id: int
    invoice_number: Optional[str] = None
    actor_id: Optional[str] = None
    actor: Optional[str] = None
    code: Optional[str] = None   # the applied promo code, None for a manual override
    is_manual: bool = False
    discount_amount: float
    subtotal: float
    timestamp: Optional[str] = None


class DiscountReportResponse(BaseModel):
    days: int
    from_date: str
    to_date: str
    rows: List[DiscountRow]
    discount_count: int
    discount_total: float
    csv_content: str


@router.get("/api/v1/reports/discounts", response_model=DiscountReportResponse)
async def report_discounts(
    days: int = Query(30, ge=1, le=365),
    format: str = Query("json", pattern=_FMT_FORMATS),
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Every discounted sale over a window with actor / code / amount / time (F-071).

    Lists the Z-report's "original sale" rows (completed / refunded / partial —
    never held, voided or credit notes) that carried a discount, with the applied
    code (PRC-01; ``is_manual`` for a codeless ``pos.discount`` override), the
    discount amount and who rang it. Owner-scoped (SEC-02), windowed by ``days``.
    """
    role_info = await get_user_role(db, owner_id)
    if role_info["role"] != "client":
        raise HTTPException(status_code=403, detail="Only clients can view the discount report")

    client_id = role_info["entity_id"]
    now = datetime.now(timezone.utc)
    start_date = now - timedelta(days=days)

    # Original sale rows only (the Z-report bucketing): exclude held tickets, voids
    # and credit notes. ``is_distinct_from`` keeps NULL-status legacy sales in.
    not_excluded = and_(
        Transactions.status.is_distinct_from("held"),
        Transactions.status.is_distinct_from("voided"),
        Transactions.status.is_distinct_from("credit_note"),
    )
    sale_rows = (
        await db.execute(
            select(Transactions).where(
                and_(
                    Transactions.client_id == client_id,
                    Transactions.created_at >= start_date,
                    func.coalesce(Transactions.discount_amount, 0.0) > 0.005,
                    not_excluded,
                )
            )
        )
    ).scalars().all()

    rows: List[DiscountRow] = []
    discount_total = 0.0
    for t in sale_rows:
        amount = round(float(t.discount_amount or 0), 2)
        discount_total += amount
        code = (t.discount_code or "").strip() or None
        rows.append(
            DiscountRow(
                transaction_id=t.id,
                invoice_number=t.invoice_number,
                actor_id=t.user_id,
                code=code,
                is_manual=code is None,
                discount_amount=amount,
                subtotal=round(float(t.subtotal or 0), 2),
                timestamp=t.created_at.isoformat() if t.created_at else None,
            )
        )

    name_map = await _resolve_actor_names(db, [r.actor_id for r in rows])
    for r in rows:
        r.actor = name_map.get(r.actor_id or "", r.actor_id)

    rows.sort(key=lambda r: (r.timestamp or ""), reverse=True)
    discount_count = len(rows)
    discount_total = round(discount_total, 2)

    # ---- CSV ----
    output = io.StringIO()
    writer = csv.writer(output)
    period_label = f"{start_date.date().isoformat()}..{now.date().isoformat()}"
    writer.writerow(["Discounts", period_label])
    writer.writerow(["Invoice", "Actor", "Code", "Discount", "Subtotal", "Timestamp"])
    for r in rows:
        writer.writerow(
            [r.invoice_number or "", r.actor or "", r.code or "manual",
             f"{r.discount_amount:.2f}", f"{r.subtotal:.2f}", r.timestamp or ""]
        )
    writer.writerow([])
    writer.writerow(
        ["Discount count", discount_count, "Discount total", f"{discount_total:.2f}"]
    )

    resp = DiscountReportResponse(
        days=days,
        from_date=start_date.date().isoformat(),
        to_date=now.date().isoformat(),
        rows=rows,
        discount_count=discount_count,
        discount_total=discount_total,
        csv_content=output.getvalue(),
    )
    if format == "pdf":
        return _pdf_discounts(resp)
    return resp


# ============================================================
# PROFIT & LOSS STATEMENT (M9, F-068) — the income statement
# ============================================================
# The single most-requested financial report for a POS buyer: a period income
# statement. Net revenue (ex-VAT, discounts netted) − COGS (rolled up from the
# bill of materials when a parent carries no own cost) = gross profit; less
# operating expenses (by category) = net profit. Aggregated entirely by the
# financial-reporting service (services.financial_reports) — SQL sums plus one
# bounded items_json stream for COGS (OPS-05), tenant-scoped, on the read replica.


class PnlExpenseRow(BaseModel):
    category: str
    amount: float


class PnlResponse(BaseModel):
    days: int
    from_date: str
    to_date: str
    gross_sales: float
    discounts: float
    net_revenue: float
    vat: float
    cogs: float
    gross_profit: float
    gross_margin_pct: float
    expenses: List[PnlExpenseRow]
    total_expenses: float
    net_profit: float
    net_margin_pct: float
    csv_content: str


def _pdf_pnl(resp: "PnlResponse") -> Response:
    pnl_rows = [
        [("الإيراد الإجمالي", "Gross sales"), _m(resp.gross_sales)],
        [("الخصومات", "Discounts"), _m(-resp.discounts)],
        [("صافي الإيراد", "Net revenue"), _m(resp.net_revenue)],
        [("تكلفة البضاعة", "COGS"), _m(-resp.cogs)],
        [("إجمالي الربح", "Gross profit"), _m(resp.gross_profit)],
        [("هامش الربح الإجمالي %", "Gross margin %"), _m(resp.gross_margin_pct)],
    ]
    expense_rows = [[e.category, _m(-e.amount)] for e in resp.expenses]
    expense_rows.append([("إجمالي المصروفات", "Total expenses"), _m(-resp.total_expenses)])
    sections = [
        {
            "heading": ("الأرباح والخسائر", "Profit & Loss"),
            "columns": [("البند", "Line"), ("المبلغ", "Amount")],
            "rows": pnl_rows,
            "widths": [120, 60],
        },
        {
            "heading": ("المصروفات التشغيلية", "Operating expenses"),
            "columns": [("الفئة", "Category"), ("المبلغ", "Amount")],
            "rows": expense_rows,
            "widths": [120, 60],
        },
    ]
    meta = [
        (("الفترة", "Period"), f"{resp.from_date}..{resp.to_date}"),
        (("صافي الربح", "Net profit"), _m(resp.net_profit)),
        (("هامش صافي الربح %", "Net margin %"), _m(resp.net_margin_pct)),
    ]
    return _report_pdf(("قائمة الأرباح والخسائر", "Profit & Loss"), meta, sections, "pnl")


@router.get("/api/v1/reports/pnl", response_model=PnlResponse)
async def report_pnl(
    days: int = Query(30, ge=1, le=365),
    format: str = Query("json", pattern=_FMT_FORMATS),
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_read_db),
):
    """Profit & Loss statement for the trailing ``days`` window (F-068).

    Net revenue − COGS = gross profit; less operating expenses = net profit. COGS
    rolls the bill of materials up onto BOM-backed parents. Owner-scoped (SEC-02),
    aggregated server-side (OPS-05), routed to the read replica so it never
    contends with the sale path.
    """
    from services.financial_reports import compute_pnl

    role_info = await get_user_role(db, owner_id)
    if role_info["role"] != "client":
        raise HTTPException(status_code=403, detail="Only clients can view the P&L report")

    client_id = role_info["entity_id"]
    now = datetime.now(timezone.utc)
    start_date = now - timedelta(days=days)
    data = await compute_pnl(db, client_id, start_date, now)

    # ---- CSV (income-statement lines + an expense breakdown) ----
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Line", "Amount"])
    writer.writerow(["Gross sales", f"{data['gross_sales']:.2f}"])
    writer.writerow(["Discounts", f"{-data['discounts']:.2f}"])
    writer.writerow(["Net revenue", f"{data['net_revenue']:.2f}"])
    writer.writerow(["COGS", f"{-data['cogs']:.2f}"])
    writer.writerow(["Gross profit", f"{data['gross_profit']:.2f}"])
    writer.writerow(["Gross margin %", f"{data['gross_margin_pct']:.2f}"])
    writer.writerow([])
    writer.writerow(["Operating expenses", ""])
    for e in data["expenses"]:
        writer.writerow([e["category"], f"{-e['amount']:.2f}"])
    writer.writerow(["Total expenses", f"{-data['total_expenses']:.2f}"])
    writer.writerow([])
    writer.writerow(["Net profit", f"{data['net_profit']:.2f}"])
    writer.writerow(["Net margin %", f"{data['net_margin_pct']:.2f}"])

    resp = PnlResponse(
        days=days,
        from_date=start_date.date().isoformat(),
        to_date=now.date().isoformat(),
        expenses=[PnlExpenseRow(**e) for e in data["expenses"]],
        csv_content=output.getvalue(),
        **{k: data[k] for k in (
            "gross_sales", "discounts", "net_revenue", "vat", "cogs",
            "gross_profit", "gross_margin_pct", "total_expenses",
            "net_profit", "net_margin_pct",
        )},
    )
    if format == "pdf":
        return _pdf_pnl(resp)
    return resp


# ============================================================
# CASH FLOW STATEMENT (M9, F-068) — cash-basis money movement
# ============================================================
# Cash basis: customer receipts (every tender, net of refunds) − cash operating
# expenses = net operating cash flow. The receipts-by-tender split and the
# cash-drawer movement totals (pay-in/pay-out/cash-drop) are surfaced alongside
# for traceability but kept out of the operating-cash-flow net (they are drawer
# float management, not business cash flow). Aggregated server-side, tenant-scoped,
# on the read replica.


class CashFlowLine(BaseModel):
    label: str
    amount: float


class CashFlowTender(BaseModel):
    tender_type: str
    collected: float
    refunds: float
    net: float


class CashFlowDrawer(BaseModel):
    pay_in: float
    pay_out: float
    cash_drop: float
    net_drawer: float


class CashFlowResponse(BaseModel):
    days: int
    from_date: str
    to_date: str
    receipts_collected: float
    receipts_refunds: float
    receipts_net: float
    by_tender: List[CashFlowTender]
    expenses: List[PnlExpenseRow]
    total_expenses: float
    inflows: List[CashFlowLine]
    outflows: List[CashFlowLine]
    net_cash_flow: float
    drawer_movements: CashFlowDrawer
    csv_content: str


def _pdf_cash_flow(resp: "CashFlowResponse") -> Response:
    flow_rows = [[i.label, _m(i.amount)] for i in resp.inflows]
    flow_rows += [[o.label, _m(-o.amount)] for o in resp.outflows]
    flow_rows.append([("صافي التدفق النقدي", "Net cash flow"), _m(resp.net_cash_flow)])
    tender_rows = [[t.tender_type, _m(t.collected), _m(t.refunds), _m(t.net)] for t in resp.by_tender]
    d = resp.drawer_movements
    drawer_rows = [
        [("إيداع نقدي", "Cash pay-in"), _m(d.pay_in)],
        [("سحب نقدي", "Cash pay-out"), _m(-d.pay_out)],
        [("ترحيل نقدي", "Cash drop"), _m(-d.cash_drop)],
        [("صافي حركة الدرج", "Net drawer change"), _m(d.net_drawer)],
    ]
    sections = [
        {
            "heading": ("التدفق النقدي التشغيلي", "Operating cash flow"),
            "columns": [("البند", "Line"), ("المبلغ", "Amount")],
            "rows": flow_rows,
            "widths": [120, 60],
        },
        {
            "heading": ("المقبوضات حسب طريقة الدفع", "Receipts by tender"),
            "columns": [("الطريقة", "Method"), ("المحصّل", "Collected"),
                        ("المرتجع", "Refunds"), ("الصافي", "Net")],
            "rows": tender_rows,
        },
        {
            "heading": ("حركات درج النقد", "Cash-drawer movements"),
            "columns": [("البند", "Line"), ("المبلغ", "Amount")],
            "rows": drawer_rows,
            "widths": [120, 60],
        },
    ]
    meta = [
        (("الفترة", "Period"), f"{resp.from_date}..{resp.to_date}"),
        (("صافي التدفق النقدي", "Net cash flow"), _m(resp.net_cash_flow)),
    ]
    return _report_pdf(("قائمة التدفقات النقدية", "Cash Flow"), meta, sections, "cash-flow")


@router.get("/api/v1/reports/cash-flow", response_model=CashFlowResponse)
async def report_cash_flow(
    days: int = Query(30, ge=1, le=365),
    format: str = Query("json", pattern=_FMT_FORMATS),
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_read_db),
):
    """Cash-basis Cash Flow statement for the trailing ``days`` window (F-068).

    Operating cash flow = customer receipts (net of refunds) − cash operating
    expenses, with a receipts-by-tender split and the drawer-movement totals shown
    for traceability. Owner-scoped (SEC-02), aggregated server-side (OPS-05),
    routed to the read replica.
    """
    from services.financial_reports import compute_cash_flow

    role_info = await get_user_role(db, owner_id)
    if role_info["role"] != "client":
        raise HTTPException(status_code=403, detail="Only clients can view the cash-flow report")

    client_id = role_info["entity_id"]
    now = datetime.now(timezone.utc)
    start_date = now - timedelta(days=days)
    data = await compute_cash_flow(db, client_id, start_date, now)

    # ---- CSV (operating-flow lines + tender split + drawer movements) ----
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Line", "Amount"])
    for i in data["inflows"]:
        writer.writerow([i["label"], f"{i['amount']:.2f}"])
    for o in data["outflows"]:
        writer.writerow([o["label"], f"{-o['amount']:.2f}"])
    writer.writerow(["Net cash flow", f"{data['net_cash_flow']:.2f}"])
    writer.writerow([])
    writer.writerow(["Receipts by tender", "Collected", "Refunds", "Net"])
    for t in data["by_tender"]:
        writer.writerow([t["tender_type"], f"{t['collected']:.2f}", f"{t['refunds']:.2f}", f"{t['net']:.2f}"])
    writer.writerow([])
    dm = data["drawer_movements"]
    writer.writerow(["Cash-drawer movements", ""])
    writer.writerow(["Cash pay-in", f"{dm['pay_in']:.2f}"])
    writer.writerow(["Cash pay-out", f"{-dm['pay_out']:.2f}"])
    writer.writerow(["Cash drop", f"{-dm['cash_drop']:.2f}"])
    writer.writerow(["Net drawer change", f"{dm['net_drawer']:.2f}"])

    resp = CashFlowResponse(
        days=days,
        from_date=start_date.date().isoformat(),
        to_date=now.date().isoformat(),
        receipts_collected=data["receipts_collected"],
        receipts_refunds=data["receipts_refunds"],
        receipts_net=data["receipts_net"],
        by_tender=[CashFlowTender(**t) for t in data["by_tender"]],
        expenses=[PnlExpenseRow(**e) for e in data["expenses"]],
        total_expenses=data["total_expenses"],
        inflows=[CashFlowLine(**i) for i in data["inflows"]],
        outflows=[CashFlowLine(**o) for o in data["outflows"]],
        net_cash_flow=data["net_cash_flow"],
        drawer_movements=CashFlowDrawer(**data["drawer_movements"]),
        csv_content=output.getvalue(),
    )
    if format == "pdf":
        return _pdf_cash_flow(resp)
    return resp


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
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Z-report (closed shift) / X-report (open shift): tenders, VAT, discounts,
    voids, refunds and cash variance for a single shift (RPT-06)."""
    role_info = await get_user_role(db, owner_id)
    if role_info["role"] != "client":
        raise HTTPException(status_code=403, detail="Only clients can access reports")

    client_id = role_info["entity_id"]
    shift = await _resolve_shift(db, owner_id, shift_id)
    if not shift:
        detail = "Shift not found" if shift_id is not None else "No open shift to report on"
        raise HTTPException(status_code=404, detail=detail)

    data = await _aggregate_zreport(db, client_id, shift)
    return ZReportResponse(**data)


@router.get("/api/v1/reports/zreport/document", response_class=HTMLResponse)
async def get_zreport_document(
    shift_id: Optional[int] = Query(None, description="Shift to print; omit for the current open shift"),
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Render the Z/X-report as an **always-Arabic** print-ready document (PRN-05).

    Enforces the fiscal/management-document Arabic rule (SRS §7) server-side: the
    report renders RTL/Arabic regardless of the caller's UI language. Print-to-PDF
    ready in any browser (80mm or A4)."""
    from services.production import PDFInvoiceService

    role_info = await get_user_role(db, owner_id)
    if role_info["role"] != "client":
        raise HTTPException(status_code=403, detail="Only clients can access reports")

    client_id = role_info["entity_id"]
    shift = await _resolve_shift(db, owner_id, shift_id)
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
        # ISSUE-077: a *newly* appearing alert is delivered out-of-band over the
        # user's enabled channels (the dispatcher honors their notification prefs).
        # Only on first appearance — re-materialization of an existing alert
        # refreshes the row in place above and never re-sends. Best-effort: a
        # delivery hiccup must never blank the in-app feed.
        try:
            await NotificationDispatcher.dispatch(
                db, user_id, type=type, title=title, message=message
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Notification delivery failed for %s: %s", dedupe_key, exc)


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
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Get the persisted notification feed for the current user (UX-08).

    For a client, refresh the system-alert feed first (idempotent upsert by
    ``dedupe_key`` — preserves read state), then return every persisted row owned
    by this user, newest first.
    """
    user_id = owner_id
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
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Persist a read acknowledgment (UX-08).

    With a ``notification_id``, mark that one row read; without one, mark the
    caller's whole feed read. Scoped to ``user_id`` so a client can only
    acknowledge their own notifications — acknowledging a row that isn't theirs (or
    doesn't exist) is a 404 (SEC-02).
    """
    user_id = owner_id

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