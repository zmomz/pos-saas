import json
import logging
from typing import List, Optional

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.product_variants import Product_variantsService
from dependencies.auth import get_admin_user, get_current_user
from dependencies.tenancy import TenantScope, get_tenant_scope
from schemas.auth import UserResponse

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/product_variants", tags=["product_variants"])


# ---------- Pydantic Schemas ----------
class Product_variantsData(BaseModel):
    """Entity data schema (for create/update)"""
    client_id: int
    product_id: int
    name: str
    attributes: str = None
    sku: str = None
    barcode: str = None
    price: float = None
    cost_price: float = None
    quantity: int = None
    is_active: bool = None


class Product_variantsUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    client_id: Optional[int] = None
    product_id: Optional[int] = None
    name: Optional[str] = None
    attributes: Optional[str] = None
    sku: Optional[str] = None
    barcode: Optional[str] = None
    price: Optional[float] = None
    cost_price: Optional[float] = None
    quantity: Optional[int] = None
    is_active: Optional[bool] = None


class Product_variantsResponse(BaseModel):
    """Entity response schema"""
    id: int
    user_id: str
    client_id: Optional[int] = None
    product_id: int
    name: str
    attributes: Optional[str] = None
    sku: Optional[str] = None
    barcode: Optional[str] = None
    price: Optional[float] = None
    cost_price: Optional[float] = None
    quantity: Optional[int] = None
    is_active: Optional[bool] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class Product_variantsListResponse(BaseModel):
    """List response schema"""
    items: List[Product_variantsResponse]
    total: int
    skip: int
    limit: int


class Product_variantsBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[Product_variantsData]


class Product_variantsBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: Product_variantsUpdateData


class Product_variantsBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[Product_variantsBatchUpdateItem]


class Product_variantsBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=Product_variantsListResponse)
async def query_product_variantss(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Query product_variantss with filtering, sorting, and pagination (user can only see their own records)"""
    logger.debug(f"Querying product_variantss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = Product_variantsService(db)
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
            user_id=scope.owner_user_id,
        )
        logger.debug(f"Found {result['total']} product_variantss")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying product_variantss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=Product_variantsListResponse)
async def query_product_variantss_all(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    # Query product_variantss with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying product_variantss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = Product_variantsService(db)
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
        logger.debug(f"Found {result['total']} product_variantss")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying product_variantss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=Product_variantsResponse)
async def get_product_variants(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Get a single product_variants by ID (user can only see their own records)"""
    logger.debug(f"Fetching product_variants with id: {id}, fields={fields}")

    service = Product_variantsService(db)
    try:
        result = await service.get_by_id(id, user_id=scope.owner_user_id)
        if not result:
            logger.warning(f"Product_variants with id {id} not found")
            raise HTTPException(status_code=404, detail="Product_variants not found")

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching product_variants {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=Product_variantsResponse, status_code=201)
async def create_product_variants(
    data: Product_variantsData,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Create a new product_variants"""
    logger.debug(f"Creating new product_variants with data: {data}")

    service = Product_variantsService(db)
    try:
        result = await service.create(data.model_dump(), user_id=(scope.owner_user_id or str(current_user.id)))
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create product_variants")

        logger.info(f"Product_variants created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating product_variants: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating product_variants: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[Product_variantsResponse], status_code=201)
async def create_product_variantss_batch(
    request: Product_variantsBatchCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Create multiple product_variantss in a single request"""
    logger.debug(f"Batch creating {len(request.items)} product_variantss")

    service = Product_variantsService(db)
    results = []

    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump(), user_id=(scope.owner_user_id or str(current_user.id)))
            if result:
                results.append(result)

        logger.info(f"Batch created {len(results)} product_variantss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[Product_variantsResponse])
async def update_product_variantss_batch(
    request: Product_variantsBatchUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Update multiple product_variantss in a single request (requires ownership)"""
    logger.debug(f"Batch updating {len(request.items)} product_variantss")

    service = Product_variantsService(db)
    results = []

    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict, user_id=scope.owner_user_id)
            if result:
                results.append(result)

        logger.info(f"Batch updated {len(results)} product_variantss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=Product_variantsResponse)
async def update_product_variants(
    id: int,
    data: Product_variantsUpdateData,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing product_variants (requires ownership)"""
    logger.debug(f"Updating product_variants {id} with data: {data}")

    service = Product_variantsService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict, user_id=scope.owner_user_id)
        if not result:
            logger.warning(f"Product_variants with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Product_variants not found")

        logger.info(f"Product_variants {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating product_variants {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating product_variants {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_product_variantss_batch(
    request: Product_variantsBatchDeleteRequest,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple product_variantss by their IDs (requires ownership)"""
    logger.debug(f"Batch deleting {len(request.ids)} product_variantss")

    service = Product_variantsService(db)
    deleted_count = 0

    try:
        for item_id in request.ids:
            success = await service.delete(item_id, user_id=scope.owner_user_id)
            if success:
                deleted_count += 1

        logger.info(f"Batch deleted {deleted_count} product_variantss successfully")
        return {"message": f"Successfully deleted {deleted_count} product_variantss", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_product_variants(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Delete a single product_variants by ID (requires ownership)"""
    logger.debug(f"Deleting product_variants with id: {id}")

    service = Product_variantsService(db)
    try:
        success = await service.delete(id, user_id=scope.owner_user_id)
        if not success:
            logger.warning(f"Product_variants with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Product_variants not found")

        logger.info(f"Product_variants {id} deleted successfully")
        return {"message": "Product_variants deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting product_variants {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
