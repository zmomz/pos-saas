"""Operator admin console (M10 Admin, #225).

Platform-master surface for running the platform itself — the first slice being
**maintenance mode**. Every route here is master-only (``scope.is_master``); a
tenant operator has no business toggling platform-global state, so they are
refused with 403.

Enforcement of maintenance mode (refusing tenant traffic with 503 while it is on)
lives in :mod:`middlewares.maintenance`; this router is only the read/write
control plane the console drives.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.tenancy import TenantScope, get_tenant_scope
from services.platform_settings import get_maintenance_state, set_maintenance_state

# Import the model so create_all/metadata registers the table (mirrors the
# suppliers router importing the supplier-credit ledger).
from models.platform_settings import PlatformSetting  # noqa: F401

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


class MaintenanceState(BaseModel):
    enabled: bool
    message: Optional[str] = None


def _require_master(scope: TenantScope) -> None:
    """Reject anyone but the platform master (403)."""
    if not scope.is_master:
        raise HTTPException(status_code=403, detail="Platform master only")


@router.get("/maintenance", response_model=MaintenanceState)
async def read_maintenance(
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Read the current platform maintenance state (master only)."""
    _require_master(scope)
    return MaintenanceState(**await get_maintenance_state(db))


@router.put("/maintenance", response_model=MaintenanceState)
async def update_maintenance(
    payload: MaintenanceState,
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Toggle platform maintenance mode on/off (master only)."""
    _require_master(scope)
    state = await set_maintenance_state(
        db, enabled=payload.enabled, message=payload.message, updated_by=scope.user_id
    )
    return MaintenanceState(**state)
