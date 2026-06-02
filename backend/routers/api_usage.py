import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.api_usage import Api_usageService
from dependencies.auth import get_current_user
from schemas.auth import UserResponse

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/api_usage", tags=["api_usage"])


# ---------- Pydantic Schemas ----------
class Api_usageData(BaseModel):
    """Entity data schema (for create/update)"""
    agent_id: int = None
    endpoint: str
    method: str
    status_code: int = None
    response_time_ms: int = None
    request_date: str = None


class Api_usageUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    agent_id: Optional[int] = None
    endpoint: Optional[str] = None
    method: Optional[str] = None
    status_code: Optional[int] = None
    response_time_ms: Optional[int] = None
    request_date: Optional[str] = None


class Api_usageResponse(BaseModel):
    """Entity response schema"""
    id: int
    user_id: str
    agent_id: Optional[int] = None
    endpoint: str
    method: str
    status_code: Optional[int] = None
    response_time_ms: Optional[int] = None
    request_date: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class Api_usageListResponse(BaseModel):
    """List response schema"""
    items: List[Api_usageResponse]
    total: int
    skip: int
    limit: int


class Api_usageBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[Api_usageData]


class Api_usageBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: Api_usageUpdateData


class Api_usageBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[Api_usageBatchUpdateItem]


class Api_usageBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=Api_usageListResponse)
async def query_api_usages(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Query api_usages with filtering, sorting, and pagination (user can only see their own records)"""
    logger.debug(f"Querying api_usages: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = Api_usageService(db)
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
        logger.debug(f"Found {result['total']} api_usages")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying api_usages: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=Api_usageListResponse)
async def query_api_usages_all(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    # Query api_usages with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying api_usages: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = Api_usageService(db)
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
        logger.debug(f"Found {result['total']} api_usages")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying api_usages: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=Api_usageResponse)
async def get_api_usage(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single api_usage by ID (user can only see their own records)"""
    logger.debug(f"Fetching api_usage with id: {id}, fields={fields}")
    
    service = Api_usageService(db)
    try:
        result = await service.get_by_id(id, user_id=str(current_user.id))
        if not result:
            logger.warning(f"Api_usage with id {id} not found")
            raise HTTPException(status_code=404, detail="Api_usage not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching api_usage {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=Api_usageResponse, status_code=201)
async def create_api_usage(
    data: Api_usageData,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new api_usage"""
    logger.debug(f"Creating new api_usage with data: {data}")
    
    service = Api_usageService(db)
    try:
        result = await service.create(data.model_dump(), user_id=str(current_user.id))
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create api_usage")
        
        logger.info(f"Api_usage created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating api_usage: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating api_usage: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[Api_usageResponse], status_code=201)
async def create_api_usages_batch(
    request: Api_usageBatchCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create multiple api_usages in a single request"""
    logger.debug(f"Batch creating {len(request.items)} api_usages")
    
    service = Api_usageService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump(), user_id=str(current_user.id))
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} api_usages successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[Api_usageResponse])
async def update_api_usages_batch(
    request: Api_usageBatchUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update multiple api_usages in a single request (requires ownership)"""
    logger.debug(f"Batch updating {len(request.items)} api_usages")
    
    service = Api_usageService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict, user_id=str(current_user.id))
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} api_usages successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=Api_usageResponse)
async def update_api_usage(
    id: int,
    data: Api_usageUpdateData,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing api_usage (requires ownership)"""
    logger.debug(f"Updating api_usage {id} with data: {data}")

    service = Api_usageService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict, user_id=str(current_user.id))
        if not result:
            logger.warning(f"Api_usage with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Api_usage not found")
        
        logger.info(f"Api_usage {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating api_usage {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating api_usage {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_api_usages_batch(
    request: Api_usageBatchDeleteRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple api_usages by their IDs (requires ownership)"""
    logger.debug(f"Batch deleting {len(request.ids)} api_usages")
    
    service = Api_usageService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id, user_id=str(current_user.id))
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} api_usages successfully")
        return {"message": f"Successfully deleted {deleted_count} api_usages", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_api_usage(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a single api_usage by ID (requires ownership)"""
    logger.debug(f"Deleting api_usage with id: {id}")
    
    service = Api_usageService(db)
    try:
        success = await service.delete(id, user_id=str(current_user.id))
        if not success:
            logger.warning(f"Api_usage with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Api_usage not found")
        
        logger.info(f"Api_usage {id} deleted successfully")
        return {"message": "Api_usage deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting api_usage {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")