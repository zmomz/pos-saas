import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.api_usage import Api_usageService
from dependencies.auth import get_admin_user, get_current_user
from schemas.auth import UserResponse

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/api_usage", tags=["api_usage"])


# ---------- Pydantic Schemas ----------
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
    current_user: UserResponse = Depends(get_admin_user),
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
# NOTE: This router is intentionally READ-ONLY (finding H3). api_usage rows are a
# metering ledger: the production metering middleware
# (middlewares/production.py::_record) is their SOLE writer, inserting the model
# directly. No create/update/delete/batch endpoint is exposed here — an actor must
# not be able to fabricate, edit, or delete their own metering history.