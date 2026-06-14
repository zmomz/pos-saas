import json
import logging
import secrets
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.auth import AuthService
from services.staff_members import Staff_membersService
from dependencies.auth import get_admin_user, get_current_user
from dependencies.tenancy import TenantScope, get_tenant_scope
from schemas.auth import UserResponse

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/staff_members", tags=["staff_members"])


# ---------- Pydantic Schemas ----------
class Staff_membersData(BaseModel):
    """Entity data schema (for create/update)"""
    name: str
    email: str = None
    phone: str = None
    role: str
    is_active: bool = None
    password: Optional[str] = None  # optional initial login password; auto-generated if omitted


class Staff_membersUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


class Staff_membersResponse(BaseModel):
    """Entity response schema"""
    id: int
    user_id: str
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    role: str
    is_active: Optional[bool] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # Set only on creation when a login was freshly provisioned: the one-time temp
    # password the merchant relays to the staff member. Never persisted/re-served.
    temp_password: Optional[str] = None

    class Config:
        from_attributes = True


class Staff_membersListResponse(BaseModel):
    """List response schema"""
    items: List[Staff_membersResponse]
    total: int
    skip: int
    limit: int


class Staff_membersBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[Staff_membersData]


class Staff_membersBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: Staff_membersUpdateData


class Staff_membersBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[Staff_membersBatchUpdateItem]


class Staff_membersBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


async def _provision_staff_login(
    db: AsyncSession, email: Optional[str], password: Optional[str]
) -> Optional[str]:
    """Ensure an auth ``User`` exists for a staff member's email so they can log in.

    Tenancy resolves a cashier back to the owning merchant by matching the staff
    row's ``email`` to a ``User.email`` — but nothing created that user, so the
    login never existed (ISSUE-033). On staff create we provision (or link) it:

    * no email             → directory-only entry, no login (returns ``None``);
    * email already a user → link to the existing account, no new password (``None``);
    * otherwise            → create a least-privilege ``User`` with a temp password
      (caller-supplied or generated) flagged ``must_change_password``; return the
      generated password once so the merchant can relay it (``None`` if supplied).
    """
    if not email:
        return None

    auth = AuthService(db)
    if await auth.get_user_by_email(email):
        return None  # already a login; tenancy will map it to the owner by email

    generated = password is None
    secret = password or secrets.token_urlsafe(9)
    user = await auth.create_user(email=email, password=secret, name=None, role="user")
    user.must_change_password = True
    await db.commit()
    return secret if generated else None


# ---------- Routes ----------
@router.get("", response_model=Staff_membersListResponse)
async def query_staff_memberss(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Query staff_memberss with filtering, sorting, and pagination (user can only see their own records)"""
    logger.debug(f"Querying staff_memberss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = Staff_membersService(db)
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
        logger.debug(f"Found {result['total']} staff_memberss")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying staff_memberss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=Staff_membersListResponse)
async def query_staff_memberss_all(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    # Query staff_memberss with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying staff_memberss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = Staff_membersService(db)
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
        logger.debug(f"Found {result['total']} staff_memberss")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying staff_memberss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=Staff_membersResponse)
async def get_staff_members(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Get a single staff_members by ID (user can only see their own records)"""
    logger.debug(f"Fetching staff_members with id: {id}, fields={fields}")
    
    service = Staff_membersService(db)
    try:
        result = await service.get_by_id(id, user_id=scope.owner_user_id)
        if not result:
            logger.warning(f"Staff_members with id {id} not found")
            raise HTTPException(status_code=404, detail="Staff_members not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching staff_members {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=Staff_membersResponse, status_code=201)
async def create_staff_members(
    data: Staff_membersData,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Create a new staff_members"""
    logger.debug(f"Creating new staff_members with data: {data}")
    
    service = Staff_membersService(db)
    try:
        payload = data.model_dump()
        password = payload.pop("password", None)  # not a Staff_members column
        result = await service.create(payload, user_id=(scope.owner_user_id or str(current_user.id)))
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create staff_members")

        # Provision the auth login so the staff member can actually sign in (#33).
        temp_password = await _provision_staff_login(db, data.email, password)

        logger.info(f"Staff_members created successfully with id: {result.id}")
        response = Staff_membersResponse.model_validate(result)
        response.temp_password = temp_password
        return response
    except ValueError as e:
        logger.error(f"Validation error creating staff_members: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating staff_members: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[Staff_membersResponse], status_code=201)
async def create_staff_memberss_batch(
    request: Staff_membersBatchCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Create multiple staff_memberss in a single request"""
    logger.debug(f"Batch creating {len(request.items)} staff_memberss")
    
    service = Staff_membersService(db)
    results = []
    
    try:
        for item_data in request.items:
            payload = item_data.model_dump()
            password = payload.pop("password", None)  # not a Staff_members column
            result = await service.create(payload, user_id=(scope.owner_user_id or str(current_user.id)))
            if result:
                # Provision the login so batch-imported staff can sign in too (#33).
                await _provision_staff_login(db, item_data.email, password)
                results.append(result)

        logger.info(f"Batch created {len(results)} staff_memberss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[Staff_membersResponse])
async def update_staff_memberss_batch(
    request: Staff_membersBatchUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Update multiple staff_memberss in a single request (requires ownership)"""
    logger.debug(f"Batch updating {len(request.items)} staff_memberss")
    
    service = Staff_membersService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict, user_id=scope.owner_user_id)
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} staff_memberss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=Staff_membersResponse)
async def update_staff_members(
    id: int,
    data: Staff_membersUpdateData,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing staff_members (requires ownership)"""
    logger.debug(f"Updating staff_members {id} with data: {data}")

    service = Staff_membersService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict, user_id=scope.owner_user_id)
        if not result:
            logger.warning(f"Staff_members with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Staff_members not found")
        
        logger.info(f"Staff_members {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating staff_members {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating staff_members {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_staff_memberss_batch(
    request: Staff_membersBatchDeleteRequest,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple staff_memberss by their IDs (requires ownership)"""
    logger.debug(f"Batch deleting {len(request.ids)} staff_memberss")
    
    service = Staff_membersService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id, user_id=scope.owner_user_id)
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} staff_memberss successfully")
        return {"message": f"Successfully deleted {deleted_count} staff_memberss", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_staff_members(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Delete a single staff_members by ID (requires ownership)"""
    logger.debug(f"Deleting staff_members with id: {id}")
    
    service = Staff_membersService(db)
    try:
        success = await service.delete(id, user_id=scope.owner_user_id)
        if not success:
            logger.warning(f"Staff_members with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Staff_members not found")
        
        logger.info(f"Staff_members {id} deleted successfully")
        return {"message": "Staff_members deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting staff_members {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")