import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, BackgroundTasks, Body, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.catalog_csv import parse_products_csv, products_to_csv
from services.products import ProductsService
from services.production import fire_event_background
from dependencies.auth import get_admin_user, get_current_user
from dependencies.tenancy import TenantScope, get_tenant_scope
from schemas.auth import UserResponse

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/products", tags=["products"])


# ---------- Pydantic Schemas ----------
class ProductsData(BaseModel):
    """Entity data schema (for create/update)"""
    client_id: int
    name: str
    name_ar: str = None
    barcode: str = None
    price: float
    cost_price: float = None
    quantity: float = None
    category: str = None
    vat_rate: float = None
    is_active: bool = None
    # POS-11 (F-011): weighted / open-price configuration.
    is_weighted: bool = None
    is_open_price: bool = None
    unit_label: str = None


class ProductsUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    client_id: Optional[int] = None
    name: Optional[str] = None
    name_ar: Optional[str] = None
    barcode: Optional[str] = None
    price: Optional[float] = None
    cost_price: Optional[float] = None
    quantity: Optional[float] = None
    category: Optional[str] = None
    vat_rate: Optional[float] = None
    is_active: Optional[bool] = None
    # POS-11 (F-011): weighted / open-price configuration.
    is_weighted: Optional[bool] = None
    is_open_price: Optional[bool] = None
    unit_label: Optional[str] = None


class ProductsResponse(BaseModel):
    """Entity response schema"""
    id: int
    user_id: str
    client_id: int
    name: str
    name_ar: Optional[str] = None
    barcode: Optional[str] = None
    price: float
    cost_price: Optional[float] = None
    quantity: Optional[float] = None
    category: Optional[str] = None
    vat_rate: Optional[float] = None
    is_active: Optional[bool] = None
    # POS-11 (F-011): weighted / open-price configuration.
    is_weighted: Optional[bool] = None
    is_open_price: Optional[bool] = None
    unit_label: Optional[str] = None
    # ISSUE-065 (P2 catalog): served URL of the product image (POS tile grid).
    image_url: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ProductsListResponse(BaseModel):
    """List response schema"""
    items: List[ProductsResponse]
    total: int
    skip: int
    limit: int


class ProductsBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[ProductsData]


class ProductsBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: ProductsUpdateData


class ProductsBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[ProductsBatchUpdateItem]


class ProductsBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=ProductsListResponse)
async def query_productss(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Query productss with filtering, sorting, and pagination (user can only see their own records)"""
    logger.debug(f"Querying productss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = ProductsService(db)
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
        logger.debug(f"Found {result['total']} productss")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying productss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=ProductsListResponse)
async def query_productss_all(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    # Query productss with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying productss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = ProductsService(db)
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
        logger.debug(f"Found {result['total']} productss")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying productss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/export")
async def export_products_csv(
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Export the merchant's catalog as a downloadable CSV (owner-scoped)."""
    service = ProductsService(db)
    # Fetch all the owner's products (a catalog export is not paginated).
    result = await service.get_list(skip=0, limit=2000, user_id=scope.owner_user_id)
    csv_text = products_to_csv(result["items"])
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="products.csv"'},
    )


@router.post("/import")
async def import_products_csv(
    file: UploadFile = File(...),
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Bulk create/update the merchant's catalog from an uploaded CSV.

    Rows are upserted by ``barcode`` (a barcode matching an existing owner product
    updates it; otherwise a new product is created). Invalid rows are reported in
    ``errors`` and never silently dropped.
    """
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="CSV must be UTF-8 encoded")

    valid_rows, errors = parse_products_csv(text)

    service = ProductsService(db)
    owner_id = scope.owner_user_id or str(current_user.id)
    created = 0
    updated = 0

    for data in valid_rows:
        barcode = data.get("barcode")
        existing = None
        if barcode:
            match = await service.get_list(
                limit=1, user_id=owner_id, query_dict={"barcode": barcode}
            )
            if match["items"]:
                existing = match["items"][0]

        if existing:
            await service.update(existing.id, data, user_id=owner_id)
            updated += 1
        else:
            data.setdefault("client_id", scope.client_id or 0)
            await service.create(data, user_id=owner_id)
            created += 1

    return {
        "created": created,
        "updated": updated,
        "total_rows": len(valid_rows) + len(errors),
        "errors": errors,
    }


@router.get("/{id}", response_model=ProductsResponse)
async def get_products(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Get a single products by ID (user can only see their own records)"""
    logger.debug(f"Fetching products with id: {id}, fields={fields}")
    
    service = ProductsService(db)
    try:
        result = await service.get_by_id(id, user_id=scope.owner_user_id)
        if not result:
            logger.warning(f"Products with id {id} not found")
            raise HTTPException(status_code=404, detail="Products not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching products {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=ProductsResponse, status_code=201)
async def create_products(
    data: ProductsData,
    background_tasks: BackgroundTasks,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Create a new products"""
    logger.debug(f"Creating new products with data: {data}")

    owner_id = scope.owner_user_id or str(current_user.id)
    service = ProductsService(db)
    try:
        result = await service.create(data.model_dump(), user_id=owner_id)
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create products")

        logger.info(f"Products created successfully with id: {result.id}")
        # Domain webhook (ISSUE-051, H25): notify subscribers post-commit. Best
        # effort — a failing endpoint never affects the created product.
        background_tasks.add_task(
            fire_event_background,
            owner_id,
            "product.created",
            {"product_id": result.id, "name": result.name, "client_id": result.client_id},
        )
        return result
    except ValueError as e:
        logger.error(f"Validation error creating products: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating products: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[ProductsResponse], status_code=201)
async def create_productss_batch(
    request: ProductsBatchCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Create multiple productss in a single request"""
    logger.debug(f"Batch creating {len(request.items)} productss")
    
    service = ProductsService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump(), user_id=(scope.owner_user_id or str(current_user.id)))
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} productss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[ProductsResponse])
async def update_productss_batch(
    request: ProductsBatchUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Update multiple productss in a single request (requires ownership)"""
    logger.debug(f"Batch updating {len(request.items)} productss")
    
    service = ProductsService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict, user_id=scope.owner_user_id)
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} productss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=ProductsResponse)
async def update_products(
    id: int,
    data: ProductsUpdateData,
    background_tasks: BackgroundTasks,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing products (requires ownership)"""
    logger.debug(f"Updating products {id} with data: {data}")

    owner_id = scope.owner_user_id or str(current_user.id)
    service = ProductsService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict, user_id=scope.owner_user_id)
        if not result:
            logger.warning(f"Products with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Products not found")

        logger.info(f"Products {id} updated successfully")
        # Domain webhook (ISSUE-051, H25): notify subscribers of the change.
        background_tasks.add_task(
            fire_event_background,
            owner_id,
            "product.updated",
            {"product_id": result.id, "name": result.name, "client_id": result.client_id},
        )
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating products {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating products {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_productss_batch(
    request: ProductsBatchDeleteRequest,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple productss by their IDs (requires ownership)"""
    logger.debug(f"Batch deleting {len(request.ids)} productss")
    
    service = ProductsService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id, user_id=scope.owner_user_id)
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} productss successfully")
        return {"message": f"Successfully deleted {deleted_count} productss", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_products(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Delete a single products by ID (requires ownership)"""
    logger.debug(f"Deleting products with id: {id}")
    
    service = ProductsService(db)
    try:
        success = await service.delete(id, user_id=scope.owner_user_id)
        if not success:
            logger.warning(f"Products with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Products not found")
        
        logger.info(f"Products {id} deleted successfully")
        return {"message": "Products deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting products {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")