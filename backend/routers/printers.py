"""Saved-printer registry router (ISSUE-047, H26/U5.2).

CRUD over a merchant's registered printers plus a routing-resolution endpoint.
A printer carries a ``role`` (receipt/kot), an optional ``station_id`` (KOT →
prep station), and an ``is_default`` flag; the resolver (``GET /resolve``)
returns which printer a printable of a given role/station routes to. Every
read/write is scoped to the caller's owner ``user_id`` (SEC-02).
"""
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.auth import get_current_user
from dependencies.tenancy import TenantScope, get_tenant_scope
from schemas.auth import UserResponse
from services.printers import ROLES, PrintersService, resolve_printer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/printers", tags=["printers"])


class PrinterData(BaseModel):
    name: str
    role: str = "receipt"
    station_id: Optional[int] = None
    device_id: Optional[str] = None
    paper_size: Optional[str] = None
    is_default: Optional[bool] = None
    client_id: Optional[int] = None
    status: Optional[str] = "active"


class PrinterUpdateData(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    station_id: Optional[int] = None
    device_id: Optional[str] = None
    paper_size: Optional[str] = None
    is_default: Optional[bool] = None
    status: Optional[str] = None


class PrinterResponse(BaseModel):
    id: int
    user_id: str
    client_id: Optional[int] = None
    name: str
    role: str
    station_id: Optional[int] = None
    device_id: Optional[str] = None
    paper_size: Optional[str] = None
    is_default: Optional[bool] = None
    status: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


def _validate_role(role: Optional[str]) -> None:
    if role is not None and role not in ROLES:
        raise HTTPException(status_code=400, detail=f"role must be one of {ROLES}")


@router.get("", response_model=List[PrinterResponse])
async def list_printers(
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """List the caller's registered printers (newest first)."""
    service = PrintersService(db)
    return await service.list(scope.owner_user_id)


@router.get("/resolve", response_model=Optional[PrinterResponse])
async def resolve(
    role: str = Query(..., description="receipt | kot"),
    station_id: Optional[int] = Query(None, description="prep station id for KOT routing"),
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Resolve which printer a ``role``/``station`` printable routes to.

    Returns ``null`` when no printer is registered (the print path then falls
    back to its built-in default device-picker).
    """
    _validate_role(role)
    return await resolve_printer(db, scope.owner_user_id, role, station_id=station_id)


@router.post("", response_model=PrinterResponse, status_code=201)
async def create_printer(
    data: PrinterData,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Register a new printer for the merchant."""
    _validate_role(data.role)
    service = PrintersService(db)
    obj = await service.create(
        data.model_dump(exclude_none=True),
        user_id=(scope.owner_user_id or str(current_user.id)),
    )
    return obj


@router.put("/{printer_id}", response_model=PrinterResponse)
async def update_printer(
    printer_id: int,
    data: PrinterUpdateData,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Update a printer (e.g. flip ``is_default`` to select it)."""
    _validate_role(data.role)
    service = PrintersService(db)
    obj = await service.update(
        printer_id,
        data.model_dump(exclude_none=True),
        user_id=scope.owner_user_id,
    )
    if obj is None:
        raise HTTPException(status_code=404, detail="Printer not found")
    return obj


@router.delete("/{printer_id}")
async def delete_printer(
    printer_id: int,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Remove a printer from the registry."""
    service = PrintersService(db)
    ok = await service.delete(printer_id, user_id=scope.owner_user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Printer not found")
    return {"message": "Printer deleted", "id": printer_id}
