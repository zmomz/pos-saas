"""Promotions API — configure & preview auto-applied discounts (ISSUE-058).

A merchant configures line/category/BOGO promotions once (``/entities/promotions``);
they then **auto-apply** at checkout when a cart meets their conditions. The
``/pos/promotions/preview`` endpoint prices a cart against the owner's active rules
without ringing a sale, so the cashier can see — before tendering — which promos a
cart has earned and the total it saves.
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.tenancy import get_owner_id
from models.promotions import Promotions
from services.promotions import PromotionResult, compute_promotions, build_cart_lines, load_active_promotions

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["promotions"])


# ---------- Schemas ----------
class PromotionData(BaseModel):
    """Create/define a promotion rule (owner-scoped)."""

    name: str
    kind: str  # line | category | bogo
    disc_type: Optional[str] = "percentage"  # percentage | fixed
    value: Optional[float] = 0.0
    product_id: Optional[int] = None
    category: Optional[str] = None
    min_subtotal: Optional[float] = None
    bogo_buy_qty: Optional[int] = 1
    bogo_get_qty: Optional[int] = 1
    bogo_get_percent: Optional[float] = 100.0
    is_active: Optional[bool] = True


class PromotionResponse(BaseModel):
    id: int
    user_id: str
    name: str
    kind: str
    disc_type: Optional[str] = None
    value: Optional[float] = None
    product_id: Optional[int] = None
    category: Optional[str] = None
    min_subtotal: Optional[float] = None
    bogo_buy_qty: Optional[int] = None
    bogo_get_qty: Optional[int] = None
    bogo_get_percent: Optional[float] = None
    is_active: Optional[bool] = None

    class Config:
        from_attributes = True


class PromotionListResponse(BaseModel):
    items: List[PromotionResponse]
    total: int


class PreviewItem(BaseModel):
    product_id: Optional[int] = None
    price: float
    quantity: float


class PreviewRequest(BaseModel):
    items: List[PreviewItem]


class AppliedPromotionInfo(BaseModel):
    promotion_id: Optional[int] = None
    name: str
    kind: str
    amount: float


class PreviewResponse(BaseModel):
    total_discount: float
    applied: List[AppliedPromotionInfo]


# ---------- Endpoints ----------
@router.post("/entities/promotions", response_model=PromotionResponse, status_code=201)
async def create_promotion(
    data: PromotionData,
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Define a promotion rule scoped to the calling merchant owner."""
    obj = Promotions(user_id=str(owner_id), **data.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("/entities/promotions", response_model=PromotionListResponse)
async def list_promotions(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """List the owner's promotion rules (newest first)."""
    rows = (
        await db.execute(
            select(Promotions)
            .where(Promotions.user_id == str(owner_id))
            .order_by(Promotions.id.desc())
            .offset(skip)
            .limit(limit)
        )
    ).scalars().all()
    return PromotionListResponse(items=list(rows), total=len(rows))


@router.post("/pos/promotions/preview", response_model=PreviewResponse)
async def preview_promotions(
    data: PreviewRequest,
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Price a cart against the owner's active rules without ringing a sale (AC2)."""
    from routers.pos import get_client_for_user

    client = await get_client_for_user(db, owner_id)
    rules = await load_active_promotions(db, owner_id)
    if not rules:
        return PreviewResponse(total_discount=0.0, applied=[])
    lines = await build_cart_lines(db, client.id, data.items)
    result: PromotionResult = compute_promotions(lines, rules)
    return PreviewResponse(
        total_discount=result.total_discount,
        applied=[
            AppliedPromotionInfo(
                promotion_id=a.promotion_id, name=a.name, kind=a.kind, amount=a.amount
            )
            for a in result.applied
        ],
    )
