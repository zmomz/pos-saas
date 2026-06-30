import json
import logging
import secrets
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.auth import AuthService
from services.staff_members import Staff_membersService
from services.staff_lifecycle import (
    StaffLifecycleService,
    attendance_to_dict,
    shift_to_dict,
)
from dependencies.auth import get_admin_user, get_current_user
from dependencies.tenancy import TenantScope, get_tenant_scope
from schemas.auth import UserResponse
from utils.password_policy import enforce_password_complexity

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
    # Issue #216 — lifecycle state (active / suspended / terminated).
    status: Optional[str] = None
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


def _assert_password_complexity(password: Optional[str]) -> None:
    """Reject a caller-supplied staff password that violates policy (ISSUE-084).

    Only caller-supplied passwords are checked; auto-generated temp passwords are
    high-entropy by construction. Validated up front so a rejection never leaves a
    half-created staff row behind.
    """
    if password is None:
        return
    enforce_password_complexity(password)


async def _provision_staff_login(
    db: AsyncSession, email: Optional[str], password: Optional[str]
) -> tuple[Optional[str], Optional[str]]:
    """Ensure an auth ``User`` exists for a staff member's email so they can log in.

    Tenancy binds a cashier to the owning merchant by the staff row's
    ``login_user_id`` FK (SEC-11) — but nothing created that login, so it never
    existed (ISSUE-033). On staff create we provision it and report the id to bind:

    * no email             → directory-only entry, no login → ``(None, None)``;
    * email already a user → a pre-existing account already owns this address. We
      cannot verify the merchant controls it (it may be an attacker who
      pre-registered the email to hijack the tenant), so we do NOT bind it as a
      staff login → ``(None, None)``. A verified-link flow is a follow-up; the
      directory row stays login-less rather than fail open.
    * otherwise            → create a least-privilege ``User`` with a temp password
      (caller-supplied or generated) flagged ``must_change_password``. Return the
      new login id to bind plus the generated password once so the merchant can
      relay it (password ``None`` if the caller supplied one).

    Returns ``(login_user_id, temp_password)``.
    """
    if not email:
        return None, None

    auth = AuthService(db)
    if await auth.get_user_by_email(email):
        # SEC-11: ownership is unverified — do not bind a pre-existing account.
        return None, None

    generated = password is None
    secret = password or secrets.token_urlsafe(9)
    user = await auth.create_user(email=email, password=secret, name=None, role="user")
    user.must_change_password = True
    await db.commit()
    return user.id, (secret if generated else None)


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
    
    # Enforce the password policy before any row is written so a weak password
    # can't leave a directory entry without a working login (ISSUE-084).
    _assert_password_complexity(data.password)

    service = Staff_membersService(db)
    try:
        payload = data.model_dump()
        password = payload.pop("password", None)  # not a Staff_members column
        result = await service.create(payload, user_id=(scope.owner_user_id or str(current_user.id)))
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create staff_members")

        # Provision the auth login so the staff member can actually sign in (#33)
        # and bind it to this row by its immutable login id (SEC-11).
        login_user_id, temp_password = await _provision_staff_login(db, data.email, password)
        if login_user_id:
            result.login_user_id = login_user_id
            await db.commit()
            await db.refresh(result)

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
    
    # Reject the whole batch up front if any supplied password is too weak, so a
    # partial batch isn't committed before the bad row is reached (ISSUE-084).
    for item_data in request.items:
        _assert_password_complexity(item_data.password)

    service = Staff_membersService(db)
    results = []

    try:
        for item_data in request.items:
            payload = item_data.model_dump()
            password = payload.pop("password", None)  # not a Staff_members column
            result = await service.create(payload, user_id=(scope.owner_user_id or str(current_user.id)))
            if result:
                # Provision the login so batch-imported staff can sign in too (#33)
                # and bind it by its immutable login id (SEC-11).
                login_user_id, _temp = await _provision_staff_login(db, item_data.email, password)
                if login_user_id:
                    result.login_user_id = login_user_id
                    await db.commit()
                    await db.refresh(result)
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

# ============================================================================
# Issue #216 — Staff lifecycle: suspend/terminate, attendance, shifts, PIN.
# ============================================================================


class PinSetRequest(BaseModel):
    """Set a staff member's numeric login PIN (4–8 digits)."""
    pin: str


class AttendanceClockInRequest(BaseModel):
    branch_id: Optional[int] = None
    notes: Optional[str] = None


class AttendanceResponse(BaseModel):
    id: int
    staff_id: int
    branch_id: Optional[int] = None
    clock_in: Optional[datetime] = None
    clock_out: Optional[datetime] = None
    hours: Optional[float] = None
    notes: Optional[str] = None


class ShiftAssignRequest(BaseModel):
    starts_at: datetime
    ends_at: datetime
    branch_id: Optional[int] = None
    role: Optional[str] = None
    notes: Optional[str] = None


class ShiftResponse(BaseModel):
    id: int
    staff_id: int
    branch_id: Optional[int] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    role: Optional[str] = None
    notes: Optional[str] = None
    status: str


async def _set_status_or_404(
    db: AsyncSession, staff_id: int, owner_user_id: str, status_value: str
) -> Staff_membersResponse:
    """Shared body for the suspend/terminate/reactivate endpoints."""
    service = StaffLifecycleService(db)
    staff = await service.set_status(staff_id, owner_user_id, status_value)
    if not staff:
        raise HTTPException(status_code=404, detail="Staff_members not found")
    return Staff_membersResponse.model_validate(staff)


@router.post("/{id}/suspend", response_model=Staff_membersResponse)
async def suspend_staff_member(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Suspend a staff member — reversible access revocation (#216).

    Live tokens for their login are dropped immediately and every subsequent
    request is blocked until they are reactivated.
    """
    return await _set_status_or_404(db, id, scope.owner_user_id, "suspended")


@router.post("/{id}/terminate", response_model=Staff_membersResponse)
async def terminate_staff_member(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Terminate (off-board) a staff member — permanent access revocation (#216)."""
    return await _set_status_or_404(db, id, scope.owner_user_id, "terminated")


@router.post("/{id}/reactivate", response_model=Staff_membersResponse)
async def reactivate_staff_member(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Restore a suspended/terminated staff member to active (#216)."""
    return await _set_status_or_404(db, id, scope.owner_user_id, "active")


@router.put("/{id}/pin", response_model=Staff_membersResponse)
async def set_staff_pin(
    id: int,
    data: PinSetRequest,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Set a staff member's numeric PIN for on-terminal PIN login (#216)."""
    service = StaffLifecycleService(db)
    try:
        staff = await service.set_pin(id, scope.owner_user_id, data.pin)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not staff:
        raise HTTPException(status_code=404, detail="Staff_members not found")
    return Staff_membersResponse.model_validate(staff)


@router.delete("/{id}/pin", response_model=Staff_membersResponse)
async def clear_staff_pin(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Remove a staff member's PIN (disables PIN login for them) (#216)."""
    service = StaffLifecycleService(db)
    staff = await service.set_pin(id, scope.owner_user_id, None)
    if not staff:
        raise HTTPException(status_code=404, detail="Staff_members not found")
    return Staff_membersResponse.model_validate(staff)


@router.post("/{id}/attendance/clock-in", response_model=AttendanceResponse, status_code=201)
async def clock_in_staff_member(
    id: int,
    data: AttendanceClockInRequest = Body(default=AttendanceClockInRequest()),
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Clock a staff member in, opening an attendance record (#216)."""
    service = StaffLifecycleService(db)
    try:
        rec = await service.clock_in(id, scope.owner_user_id, data.branch_id, data.notes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return AttendanceResponse(**attendance_to_dict(rec))


@router.post("/{id}/attendance/clock-out", response_model=AttendanceResponse)
async def clock_out_staff_member(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Clock a staff member out, closing their open attendance record (#216)."""
    service = StaffLifecycleService(db)
    try:
        rec = await service.clock_out(id, scope.owner_user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return AttendanceResponse(**attendance_to_dict(rec))


@router.get("/{id}/attendance", response_model=List[AttendanceResponse])
async def list_staff_attendance(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """List a staff member's attendance records, most recent first (#216)."""
    service = StaffLifecycleService(db)
    records = await service.list_attendance(scope.owner_user_id, staff_id=id)
    return [AttendanceResponse(**attendance_to_dict(r)) for r in records]


@router.post("/{id}/shifts", response_model=ShiftResponse, status_code=201)
async def assign_staff_shift(
    id: int,
    data: ShiftAssignRequest,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Roster a staff member to a planned shift window (#216)."""
    service = StaffLifecycleService(db)
    try:
        shift = await service.assign_shift(
            id,
            scope.owner_user_id,
            starts_at=data.starts_at,
            ends_at=data.ends_at,
            branch_id=data.branch_id,
            role=data.role,
            notes=data.notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ShiftResponse(**shift_to_dict(shift))


@router.get("/{id}/shifts", response_model=List[ShiftResponse])
async def list_staff_shifts(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """List a staff member's scheduled shifts (#216)."""
    service = StaffLifecycleService(db)
    shifts = await service.list_shifts(scope.owner_user_id, staff_id=id)
    return [ShiftResponse(**shift_to_dict(s)) for s in shifts]


@router.delete("/shifts/{shift_id}", response_model=ShiftResponse)
async def cancel_staff_shift(
    shift_id: int,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Cancel a scheduled shift assignment (#216)."""
    service = StaffLifecycleService(db)
    shift = await service.cancel_shift(shift_id, scope.owner_user_id)
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")
    return ShiftResponse(**shift_to_dict(shift))


@router.get("/attendance/export")
async def export_staff_attendance_csv(
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Export the merchant's attendance/hours as CSV for payroll (export only) (#216)."""
    service = StaffLifecycleService(db)
    csv_text = await service.attendance_csv(scope.owner_user_id)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="attendance.csv"'},
    )
