import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.auth import get_current_user
from dependencies.tenancy import TenantScope, get_tenant_scope
from schemas.auth import UserResponse
from services.discount_codes import DiscountCodeError, DiscountCodesService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/discount-codes", tags=["discount-codes"])


# ---------- Pydantic Schemas ----------
class GenerateCodesRequest(BaseModel):
    """Mint a batch of single-use codes (ISSUE-059)."""

    count: int = Field(..., ge=1, le=1000)
    type: str
    value: float
    min_purchase: Optional[float] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None


class DiscountCodeResponse(BaseModel):
    id: int
    user_id: str
    batch_id: str
    code: str
    type: str
    value: float
    min_purchase: Optional[float] = None
    redeemed: bool
    redeemed_at: Optional[datetime] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class GenerateCodesResponse(BaseModel):
    batch_id: str
    count: int
    codes: List[DiscountCodeResponse]


class RedeemCodeRequest(BaseModel):
    """Redeem a single-use code against an order subtotal."""

    code: str
    subtotal: float


class RedeemCodeResponse(BaseModel):
    valid: bool
    code: str
    type: str
    value: float
    discount_amount: float


# ---------- Routes ----------
@router.post("/generate", response_model=GenerateCodesResponse, status_code=201)
async def generate_codes(
    data: GenerateCodesRequest,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Mint a batch of unique, single-use discount codes for the owner."""
    service = DiscountCodesService(db)
    result = await service.generate_batch(
        user_id=(scope.owner_user_id or str(current_user.id)),
        count=data.count,
        type=data.type,
        value=data.value,
        min_purchase=data.min_purchase,
        starts_at=data.starts_at,
        ends_at=data.ends_at,
    )
    return result


@router.post("/redeem", response_model=RedeemCodeResponse)
async def redeem_code(
    data: RedeemCodeRequest,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Redeem a unique code exactly once and return the server-priced amount.

    The one-shot consumption is authoritative: a second redemption of the same
    code — or one outside its validity window — fails with 400.
    """
    service = DiscountCodesService(db)
    try:
        out = await service.redeem(
            data.code, data.subtotal, user_id=(scope.owner_user_id or str(current_user.id))
        )
    except DiscountCodeError as e:
        logger.info("Discount-code redemption rejected: %s", str(e))
        raise HTTPException(status_code=400, detail=str(e))
    return RedeemCodeResponse(valid=True, **out)
