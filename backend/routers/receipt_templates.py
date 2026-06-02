import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.receipt_templates import Receipt_templatesService
from dependencies.auth import get_admin_user, get_current_user
from schemas.auth import UserResponse

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/receipt_templates", tags=["receipt_templates"])


# ---------- Pydantic Schemas ----------
class Receipt_templatesData(BaseModel):
    """Entity data schema (for create/update)"""
    client_id: int = None
    name: str
    header_text: str = None
    footer_text: str = None
    show_logo: bool = None
    show_vat_details: bool = None
    show_qr_code: bool = None
    paper_size: str = None
    font_size: str = None
    is_default: bool = None


class Receipt_templatesUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    client_id: Optional[int] = None
    name: Optional[str] = None
    header_text: Optional[str] = None
    footer_text: Optional[str] = None
    show_logo: Optional[bool] = None
    show_vat_details: Optional[bool] = None
    show_qr_code: Optional[bool] = None
    paper_size: Optional[str] = None
    font_size: Optional[str] = None
    is_default: Optional[bool] = None


class Receipt_templatesResponse(BaseModel):
    """Entity response schema"""
    id: int
    user_id: str
    client_id: Optional[int] = None
    name: str
    header_text: Optional[str] = None
    footer_text: Optional[str] = None
    show_logo: Optional[bool] = None
    show_vat_details: Optional[bool] = None
    show_qr_code: Optional[bool] = None
    paper_size: Optional[str] = None
    font_size: Optional[str] = None
    is_default: Optional[bool] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class Receipt_templatesListResponse(BaseModel):
    """List response schema"""
    items: List[Receipt_templatesResponse]
    total: int
    skip: int
    limit: int


class Receipt_templatesBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[Receipt_templatesData]


class Receipt_templatesBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: Receipt_templatesUpdateData


class Receipt_templatesBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[Receipt_templatesBatchUpdateItem]


class Receipt_templatesBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=Receipt_templatesListResponse)
async def query_receipt_templatess(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Query receipt_templatess with filtering, sorting, and pagination (user can only see their own records)"""
    logger.debug(f"Querying receipt_templatess: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = Receipt_templatesService(db)
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
        logger.debug(f"Found {result['total']} receipt_templatess")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying receipt_templatess: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=Receipt_templatesListResponse)
async def query_receipt_templatess_all(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    # Query receipt_templatess with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying receipt_templatess: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = Receipt_templatesService(db)
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
        logger.debug(f"Found {result['total']} receipt_templatess")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying receipt_templatess: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=Receipt_templatesResponse)
async def get_receipt_templates(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single receipt_templates by ID (user can only see their own records)"""
    logger.debug(f"Fetching receipt_templates with id: {id}, fields={fields}")
    
    service = Receipt_templatesService(db)
    try:
        result = await service.get_by_id(id, user_id=str(current_user.id))
        if not result:
            logger.warning(f"Receipt_templates with id {id} not found")
            raise HTTPException(status_code=404, detail="Receipt_templates not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching receipt_templates {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=Receipt_templatesResponse, status_code=201)
async def create_receipt_templates(
    data: Receipt_templatesData,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new receipt_templates"""
    logger.debug(f"Creating new receipt_templates with data: {data}")
    
    service = Receipt_templatesService(db)
    try:
        result = await service.create(data.model_dump(), user_id=str(current_user.id))
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create receipt_templates")
        
        logger.info(f"Receipt_templates created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating receipt_templates: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating receipt_templates: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[Receipt_templatesResponse], status_code=201)
async def create_receipt_templatess_batch(
    request: Receipt_templatesBatchCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create multiple receipt_templatess in a single request"""
    logger.debug(f"Batch creating {len(request.items)} receipt_templatess")
    
    service = Receipt_templatesService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump(), user_id=str(current_user.id))
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} receipt_templatess successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[Receipt_templatesResponse])
async def update_receipt_templatess_batch(
    request: Receipt_templatesBatchUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update multiple receipt_templatess in a single request (requires ownership)"""
    logger.debug(f"Batch updating {len(request.items)} receipt_templatess")
    
    service = Receipt_templatesService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict, user_id=str(current_user.id))
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} receipt_templatess successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=Receipt_templatesResponse)
async def update_receipt_templates(
    id: int,
    data: Receipt_templatesUpdateData,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing receipt_templates (requires ownership)"""
    logger.debug(f"Updating receipt_templates {id} with data: {data}")

    service = Receipt_templatesService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict, user_id=str(current_user.id))
        if not result:
            logger.warning(f"Receipt_templates with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Receipt_templates not found")
        
        logger.info(f"Receipt_templates {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating receipt_templates {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating receipt_templates {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_receipt_templatess_batch(
    request: Receipt_templatesBatchDeleteRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple receipt_templatess by their IDs (requires ownership)"""
    logger.debug(f"Batch deleting {len(request.ids)} receipt_templatess")
    
    service = Receipt_templatesService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id, user_id=str(current_user.id))
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} receipt_templatess successfully")
        return {"message": f"Successfully deleted {deleted_count} receipt_templatess", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_receipt_templates(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a single receipt_templates by ID (requires ownership)"""
    logger.debug(f"Deleting receipt_templates with id: {id}")
    
    service = Receipt_templatesService(db)
    try:
        success = await service.delete(id, user_id=str(current_user.id))
        if not success:
            logger.warning(f"Receipt_templates with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Receipt_templates not found")
        
        logger.info(f"Receipt_templates {id} deleted successfully")
        return {"message": "Receipt_templates deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting receipt_templates {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")