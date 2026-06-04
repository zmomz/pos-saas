import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.discounts import (
    DiscountsService,
    DiscountValidationError,
    compute_discount_amount,
)
from dependencies.auth import get_admin_user, get_current_user
from dependencies.features import require_feature
from schemas.auth import UserResponse

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/discounts", tags=["discounts"])


# ---------- Pydantic Schemas ----------
class DiscountsData(BaseModel):
    """Entity data schema (for create/update)"""
    code: str
    type: str
    value: float
    min_purchase: float = None
    is_active: bool = None
    usage_count: int = None
    max_uses: int = None


class DiscountsUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    code: Optional[str] = None
    type: Optional[str] = None
    value: Optional[float] = None
    min_purchase: Optional[float] = None
    is_active: Optional[bool] = None
    usage_count: Optional[int] = None
    max_uses: Optional[int] = None


class DiscountsResponse(BaseModel):
    """Entity response schema"""
    id: int
    user_id: str
    code: str
    type: str
    value: float
    min_purchase: Optional[float] = None
    is_active: Optional[bool] = None
    usage_count: Optional[int] = None
    max_uses: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DiscountsListResponse(BaseModel):
    """List response schema"""
    items: List[DiscountsResponse]
    total: int
    skip: int
    limit: int


class DiscountsBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[DiscountsData]


class DiscountsBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: DiscountsUpdateData


class DiscountsBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[DiscountsBatchUpdateItem]


class DiscountsBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


class DiscountValidateRequest(BaseModel):
    """Validate a discount code against an order subtotal (PRC-01)."""
    code: str
    subtotal: float


class DiscountValidateResponse(BaseModel):
    """Server-authoritative discount preview (the amount the POS must trust)."""
    valid: bool
    code: str
    type: str
    value: float
    discount_amount: float


# ---------- Routes ----------
@router.get("", response_model=DiscountsListResponse)
async def query_discountss(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Query discountss with filtering, sorting, and pagination (user can only see their own records)"""
    logger.debug(f"Querying discountss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = DiscountsService(db)
    try:
        # Parse query JSON if provided
        query_dict = None
        if query:
            try:
                query_dict = json.loads(query)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid query JSON format")
        
        result = await service.get_list(
            skip=skip, 
            limit=limit,
            query_dict=query_dict,
            sort=sort,
            user_id=str(current_user.id),
        )
        logger.debug(f"Found {result['total']} discountss")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying discountss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=DiscountsListResponse)
async def query_discountss_all(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    # Query discountss with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying discountss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = DiscountsService(db)
    try:
        # Parse query JSON if provided
        query_dict = None
        if query:
            try:
                query_dict = json.loads(query)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid query JSON format")

        result = await service.get_list(
            skip=skip,
            limit=limit,
            query_dict=query_dict,
            sort=sort
        )
        logger.debug(f"Found {result['total']} discountss")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying discountss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=DiscountsResponse)
async def get_discounts(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single discounts by ID (user can only see their own records)"""
    logger.debug(f"Fetching discounts with id: {id}, fields={fields}")
    
    service = DiscountsService(db)
    try:
        result = await service.get_by_id(id, user_id=str(current_user.id))
        if not result:
            logger.warning(f"Discounts with id {id} not found")
            raise HTTPException(status_code=404, detail="Discounts not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching discounts {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=DiscountsResponse, status_code=201)
async def create_discounts(
    data: DiscountsData,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new discounts"""
    logger.debug(f"Creating new discounts with data: {data}")
    
    service = DiscountsService(db)
    try:
        result = await service.create(data.model_dump(), user_id=str(current_user.id))
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create discounts")
        
        logger.info(f"Discounts created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating discounts: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating discounts: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post(
    "/validate",
    response_model=DiscountValidateResponse,
    dependencies=[Depends(require_feature("discounts"))],
)
async def validate_discount(
    data: DiscountValidateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Validate a discount code server-side and return the authoritative amount (PRC-01).

    The POS must not trust a client-computed discount — this endpoint is the
    source of truth for whether a code applies (active / min-purchase / usage cap)
    and how much it is worth for the given subtotal. It is read-only: it does
    **not** consume a use (the use is consumed atomically with the sale in
    ``POST /pos/transaction``). A failing code returns 400 with the reason.
    """
    logger.debug(f"Validating discount code against subtotal={data.subtotal}")

    service = DiscountsService(db)
    try:
        discount = await service.validate(
            data.code, data.subtotal, user_id=str(current_user.id)
        )
    except DiscountValidationError as e:
        logger.info(f"Discount validation rejected: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error validating discount: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

    amount = compute_discount_amount(discount, data.subtotal)
    return DiscountValidateResponse(
        valid=True,
        code=discount.code,
        type=discount.type,
        value=discount.value,
        discount_amount=amount,
    )


@router.post("/batch", response_model=List[DiscountsResponse], status_code=201)
async def create_discountss_batch(
    request: DiscountsBatchCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create multiple discountss in a single request"""
    logger.debug(f"Batch creating {len(request.items)} discountss")
    
    service = DiscountsService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump(), user_id=str(current_user.id))
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} discountss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[DiscountsResponse])
async def update_discountss_batch(
    request: DiscountsBatchUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update multiple discountss in a single request (requires ownership)"""
    logger.debug(f"Batch updating {len(request.items)} discountss")
    
    service = DiscountsService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict, user_id=str(current_user.id))
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} discountss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=DiscountsResponse)
async def update_discounts(
    id: int,
    data: DiscountsUpdateData,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing discounts (requires ownership)"""
    logger.debug(f"Updating discounts {id} with data: {data}")

    service = DiscountsService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict, user_id=str(current_user.id))
        if not result:
            logger.warning(f"Discounts with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Discounts not found")
        
        logger.info(f"Discounts {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating discounts {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating discounts {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_discountss_batch(
    request: DiscountsBatchDeleteRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple discountss by their IDs (requires ownership)"""
    logger.debug(f"Batch deleting {len(request.ids)} discountss")
    
    service = DiscountsService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id, user_id=str(current_user.id))
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} discountss successfully")
        return {"message": f"Successfully deleted {deleted_count} discountss", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_discounts(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a single discounts by ID (requires ownership)"""
    logger.debug(f"Deleting discounts with id: {id}")
    
    service = DiscountsService(db)
    try:
        success = await service.delete(id, user_id=str(current_user.id))
        if not success:
            logger.warning(f"Discounts with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Discounts not found")
        
        logger.info(f"Discounts {id} deleted successfully")
        return {"message": "Discounts deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting discounts {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")