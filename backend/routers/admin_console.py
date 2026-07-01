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
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.tenancy import TenantScope, get_tenant_scope
from services.admin_logs import list_api_logs
from services.job_queue import queue_stats
from services.platform_features import get_feature_flags, set_feature_flag
from services.platform_settings import get_maintenance_state, set_maintenance_state

# Import the model so create_all/metadata registers the table (mirrors the
# suppliers router importing the supplier-credit ledger).
from models.platform_settings import PlatformSetting  # noqa: F401

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


class MaintenanceState(BaseModel):
    enabled: bool
    message: Optional[str] = None


class FeatureFlag(BaseModel):
    key: str
    enabled: bool
    description: str


class FeatureFlagUpdate(BaseModel):
    enabled: bool


class JobQueueStatus(BaseModel):
    backend: str
    healthy: bool
    queued: int
    registered_jobs: list[str]


class ApiLogEntry(BaseModel):
    id: int
    user_id: Optional[str] = None
    owner_user_id: Optional[str] = None
    endpoint: str
    method: str
    status_code: Optional[int] = None
    response_time_ms: Optional[int] = None
    created_at: Optional[datetime] = None


class ApiLogPage(BaseModel):
    items: list[ApiLogEntry]
    total: int
    skip: int
    limit: int


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


@router.get("/feature-flags", response_model=list[FeatureFlag])
async def list_feature_flags(
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """List the declared platform feature flags with their live values (master only)."""
    _require_master(scope)
    return await get_feature_flags(db)


@router.put("/feature-flags/{key}", response_model=FeatureFlag)
async def update_feature_flag(
    key: str,
    payload: FeatureFlagUpdate,
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Toggle a single declared platform feature flag (master only)."""
    _require_master(scope)
    try:
        return await set_feature_flag(db, key, payload.enabled, updated_by=scope.user_id)
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Unknown feature flag: {key}")


@router.get("/jobs", response_model=JobQueueStatus)
async def read_job_queue(
    scope: TenantScope = Depends(get_tenant_scope),
):
    """Read the background job-queue monitor: backend, health, depth, registry (master only)."""
    _require_master(scope)
    return JobQueueStatus(**await queue_stats())


@router.get("/logs/api", response_model=ApiLogPage)
async def read_api_logs(
    skip: int = 0,
    limit: int = 50,
    errors_only: bool = False,
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Read the platform-wide per-request API/error log, newest-first (master only).

    ``errors_only`` narrows the viewer to failing requests (status_code >= 400) —
    the "error log" view. Rows are the real ``api_usage`` entries the request
    middleware writes; nothing here fabricates state.
    """
    _require_master(scope)
    return await list_api_logs(db, skip=skip, limit=min(limit, 200), errors_only=errors_only)
