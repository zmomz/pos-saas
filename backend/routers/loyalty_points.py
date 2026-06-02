import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.loyalty_points import Loyalty_pointsService
from dependencies.auth import get_admin_user, get_current_user
from schemas.auth import UserResponse

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/loyalty_points", tags=["loyalty_points"])


# ---------- Pydantic Schemas ----------
class Loyalty_pointsData(BaseModel):
    """Entity data schema (for create/update)"""
    client_id: int = None
    customer_id: int
    points_balance: int = None
    total_earned: int = None
    total_redeemed: int = None


class Loyalty_pointsUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    client_id: Optional[int] = None
    customer_id: Optional[int] = None
    points_balance: Optional[int] = None
    total_earned: Optional[int] = None
    total_redeemed: Optional[int] = None


class Loyalty_pointsResponse(BaseModel):
    """Entity response schema"""
    id: int
    user_id: str
    client_id: Optional[int] = None
    customer_id: int
    points_balance: Optional[int] = None
    total_earned: Optional[int] = None
    total_redeemed: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class Loyalty_pointsListResponse(BaseModel):
    """List response schema"""
    items: List[Loyalty_pointsResponse]
    total: int
    skip: int
    limit: int


class Loyalty_pointsBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[Loyalty_pointsData]


class Loyalty_pointsBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: Loyalty_pointsUpdateData


class Loyalty_pointsBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[Loyalty_pointsBatchUpdateItem]


class Loyalty_pointsBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=Loyalty_pointsListResponse)
async def query_loyalty_pointss(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Query loyalty_pointss with filtering, sorting, and pagination (user can only see their own records)"""
    logger.debug(f"Querying loyalty_pointss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = Loyalty_pointsService(db)
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
        logger.debug(f"Found {result['total']} loyalty_pointss")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying loyalty_pointss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=Loyalty_pointsListResponse)
async def query_loyalty_pointss_all(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    # Query loyalty_pointss with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying loyalty_pointss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = Loyalty_pointsService(db)
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
        logger.debug(f"Found {result['total']} loyalty_pointss")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying loyalty_pointss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=Loyalty_pointsResponse)
async def get_loyalty_points(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single loyalty_points by ID (user can only see their own records)"""
    logger.debug(f"Fetching loyalty_points with id: {id}, fields={fields}")
    
    service = Loyalty_pointsService(db)
    try:
        result = await service.get_by_id(id, user_id=str(current_user.id))
        if not result:
            logger.warning(f"Loyalty_points with id {id} not found")
            raise HTTPException(status_code=404, detail="Loyalty_points not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching loyalty_points {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=Loyalty_pointsResponse, status_code=201)
async def create_loyalty_points(
    data: Loyalty_pointsData,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new loyalty_points"""
    logger.debug(f"Creating new loyalty_points with data: {data}")
    
    service = Loyalty_pointsService(db)
    try:
        result = await service.create(data.model_dump(), user_id=str(current_user.id))
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create loyalty_points")
        
        logger.info(f"Loyalty_points created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating loyalty_points: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating loyalty_points: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[Loyalty_pointsResponse], status_code=201)
async def create_loyalty_pointss_batch(
    request: Loyalty_pointsBatchCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create multiple loyalty_pointss in a single request"""
    logger.debug(f"Batch creating {len(request.items)} loyalty_pointss")
    
    service = Loyalty_pointsService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump(), user_id=str(current_user.id))
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} loyalty_pointss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[Loyalty_pointsResponse])
async def update_loyalty_pointss_batch(
    request: Loyalty_pointsBatchUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update multiple loyalty_pointss in a single request (requires ownership)"""
    logger.debug(f"Batch updating {len(request.items)} loyalty_pointss")
    
    service = Loyalty_pointsService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict, user_id=str(current_user.id))
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} loyalty_pointss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=Loyalty_pointsResponse)
async def update_loyalty_points(
    id: int,
    data: Loyalty_pointsUpdateData,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing loyalty_points (requires ownership)"""
    logger.debug(f"Updating loyalty_points {id} with data: {data}")

    service = Loyalty_pointsService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict, user_id=str(current_user.id))
        if not result:
            logger.warning(f"Loyalty_points with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Loyalty_points not found")
        
        logger.info(f"Loyalty_points {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating loyalty_points {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating loyalty_points {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_loyalty_pointss_batch(
    request: Loyalty_pointsBatchDeleteRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple loyalty_pointss by their IDs (requires ownership)"""
    logger.debug(f"Batch deleting {len(request.ids)} loyalty_pointss")
    
    service = Loyalty_pointsService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id, user_id=str(current_user.id))
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} loyalty_pointss successfully")
        return {"message": f"Successfully deleted {deleted_count} loyalty_pointss", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_loyalty_points(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a single loyalty_points by ID (requires ownership)"""
    logger.debug(f"Deleting loyalty_points with id: {id}")
    
    service = Loyalty_pointsService(db)
    try:
        success = await service.delete(id, user_id=str(current_user.id))
        if not success:
            logger.warning(f"Loyalty_points with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Loyalty_points not found")
        
        logger.info(f"Loyalty_points {id} deleted successfully")
        return {"message": "Loyalty_points deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting loyalty_points {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")