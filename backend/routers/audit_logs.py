import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.audit_logs import Audit_logsService
from dependencies.auth import get_admin_user, get_current_user
from schemas.auth import UserResponse

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/audit_logs", tags=["audit_logs"])


# ---------- Pydantic Schemas ----------
class Audit_logsResponse(BaseModel):
    """Entity response schema"""
    id: int
    user_id: str
    action: str
    details: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class Audit_logsListResponse(BaseModel):
    """List response schema"""
    items: List[Audit_logsResponse]
    total: int
    skip: int
    limit: int


# ---------- Routes ----------
@router.get("", response_model=Audit_logsListResponse)
async def query_audit_logss(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Query audit_logss with filtering, sorting, and pagination (user can only see their own records)"""
    logger.debug(f"Querying audit_logss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = Audit_logsService(db)
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
        logger.debug(f"Found {result['total']} audit_logss")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying audit_logss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=Audit_logsListResponse)
async def query_audit_logss_all(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    # Query audit_logss with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying audit_logss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = Audit_logsService(db)
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
        logger.debug(f"Found {result['total']} audit_logss")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying audit_logss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=Audit_logsResponse)
async def get_audit_logs(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single audit_logs by ID (user can only see their own records)"""
    logger.debug(f"Fetching audit_logs with id: {id}, fields={fields}")
    
    service = Audit_logsService(db)
    try:
        result = await service.get_by_id(id, user_id=str(current_user.id))
        if not result:
            logger.warning(f"Audit_logs with id {id} not found")
            raise HTTPException(status_code=404, detail="Audit_logs not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching audit_logs {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
# NOTE: This router is intentionally READ-ONLY (finding H3). The audit trail is a
# compliance log: the audit middleware (middlewares/audit.py::write_audit_log) is
# its SOLE writer. No create/update/delete/batch endpoint is exposed here — an
# actor must not be able to fabricate, edit, or delete their own audit history.