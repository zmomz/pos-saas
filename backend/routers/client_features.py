import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.client_features import Client_featuresService
from dependencies.auth import get_current_user
from schemas.auth import UserResponse

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/client_features", tags=["client_features"])


# ---------- Pydantic Schemas ----------
class Client_featuresData(BaseModel):
    """Entity data schema (for create/update)"""
    client_id: int
    feature_name: str
    is_enabled: bool = None


class Client_featuresUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    client_id: Optional[int] = None
    feature_name: Optional[str] = None
    is_enabled: Optional[bool] = None


class Client_featuresResponse(BaseModel):
    """Entity response schema"""
    id: int
    user_id: str
    client_id: int
    feature_name: str
    is_enabled: Optional[bool] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class Client_featuresListResponse(BaseModel):
    """List response schema"""
    items: List[Client_featuresResponse]
    total: int
    skip: int
    limit: int


class Client_featuresBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[Client_featuresData]


class Client_featuresBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: Client_featuresUpdateData


class Client_featuresBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[Client_featuresBatchUpdateItem]


class Client_featuresBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=Client_featuresListResponse)
async def query_client_featuress(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Query client_featuress with filtering, sorting, and pagination (user can only see their own records)"""
    logger.debug(f"Querying client_featuress: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = Client_featuresService(db)
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
        logger.debug(f"Found {result['total']} client_featuress")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying client_featuress: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=Client_featuresListResponse)
async def query_client_featuress_all(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    db: AsyncSession = Depends(get_db),
):
    # Query client_featuress with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying client_featuress: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = Client_featuresService(db)
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
        logger.debug(f"Found {result['total']} client_featuress")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying client_featuress: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=Client_featuresResponse)
async def get_client_features(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single client_features by ID (user can only see their own records)"""
    logger.debug(f"Fetching client_features with id: {id}, fields={fields}")
    
    service = Client_featuresService(db)
    try:
        result = await service.get_by_id(id, user_id=str(current_user.id))
        if not result:
            logger.warning(f"Client_features with id {id} not found")
            raise HTTPException(status_code=404, detail="Client_features not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching client_features {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=Client_featuresResponse, status_code=201)
async def create_client_features(
    data: Client_featuresData,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new client_features"""
    logger.debug(f"Creating new client_features with data: {data}")
    
    service = Client_featuresService(db)
    try:
        result = await service.create(data.model_dump(), user_id=str(current_user.id))
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create client_features")
        
        logger.info(f"Client_features created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating client_features: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating client_features: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[Client_featuresResponse], status_code=201)
async def create_client_featuress_batch(
    request: Client_featuresBatchCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create multiple client_featuress in a single request"""
    logger.debug(f"Batch creating {len(request.items)} client_featuress")
    
    service = Client_featuresService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump(), user_id=str(current_user.id))
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} client_featuress successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[Client_featuresResponse])
async def update_client_featuress_batch(
    request: Client_featuresBatchUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update multiple client_featuress in a single request (requires ownership)"""
    logger.debug(f"Batch updating {len(request.items)} client_featuress")
    
    service = Client_featuresService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict, user_id=str(current_user.id))
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} client_featuress successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=Client_featuresResponse)
async def update_client_features(
    id: int,
    data: Client_featuresUpdateData,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing client_features (requires ownership)"""
    logger.debug(f"Updating client_features {id} with data: {data}")

    service = Client_featuresService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict, user_id=str(current_user.id))
        if not result:
            logger.warning(f"Client_features with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Client_features not found")
        
        logger.info(f"Client_features {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating client_features {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating client_features {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_client_featuress_batch(
    request: Client_featuresBatchDeleteRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple client_featuress by their IDs (requires ownership)"""
    logger.debug(f"Batch deleting {len(request.ids)} client_featuress")
    
    service = Client_featuresService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id, user_id=str(current_user.id))
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} client_featuress successfully")
        return {"message": f"Successfully deleted {deleted_count} client_featuress", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_client_features(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a single client_features by ID (requires ownership)"""
    logger.debug(f"Deleting client_features with id: {id}")
    
    service = Client_featuresService(db)
    try:
        success = await service.delete(id, user_id=str(current_user.id))
        if not success:
            logger.warning(f"Client_features with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Client_features not found")
        
        logger.info(f"Client_features {id} deleted successfully")
        return {"message": "Client_features deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting client_features {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")