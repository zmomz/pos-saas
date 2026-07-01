import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.audit_logs import Audit_logsService
from services.audit import build_regulatory_audit_export
from dependencies.auth import get_admin_user, get_current_user
from dependencies.tenancy import TenantScope, get_tenant_scope
from schemas.auth import UserResponse

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/audit_logs", tags=["audit_logs"])


# ---------- Pydantic Schemas ----------
class Audit_logsResponse(BaseModel):
    """Entity response schema"""
    id: int
    user_id: str
    # The actor's email, resolved from ``user_id`` so the AuditLog User column
    # shows who acted rather than a bare id (None if the user row is gone).
    user_email: Optional[str] = None
    owner_user_id: Optional[str] = None
    # Normalized verb (create/update/delete/sale/export/auth_failure/other) the UI
    # badges and the action filter match against — see services.audit_logs.
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


class RegulatoryExportIntegrity(BaseModel):
    """Reconcile status of the audit trail (outcome of ``verify_audit_chain``)."""
    verified: bool
    checked: int
    broken_id: Optional[int] = None
    reason: Optional[str] = None


class RegulatoryAuditRecord(BaseModel):
    """A raw audit row, chain hashes included, for independent re-verification."""
    id: int
    user_id: str
    owner_user_id: Optional[str] = None
    action: str
    details: Optional[str] = None
    ip_address: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    changes: Optional[str] = None
    prev_hash: Optional[str] = None
    row_hash: Optional[str] = None
    created_at: Optional[datetime] = None


class RegulatoryAuditExportResponse(BaseModel):
    """A self-describing, independently verifiable regulatory audit artifact."""
    artifact_type: str
    format_version: str
    generated_at: datetime
    owner_user_id: Optional[str] = None
    record_count: int
    integrity: RegulatoryExportIntegrity
    records: List[RegulatoryAuditRecord]


# ---------- Routes ----------
@router.get("", response_model=Audit_logsListResponse)
async def query_audit_logss(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Query audit_logss scoped to the caller's tenant (owner sees staff actions)"""
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
            owner_user_id=scope.owner_user_id,
        )
        result["items"] = await service.render_rows(result["items"])
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
        result["items"] = await service.render_rows(result["items"])
        logger.debug(f"Found {result['total']} audit_logss")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying audit_logss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/regulatory-export", response_model=RegulatoryAuditExportResponse)
async def regulatory_audit_export(
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Produce a compliant regulatory audit-trail artifact for the caller's tenant.

    Owner-scoped (SEC-02): a tenant gets only its own audit rows (the platform
    master gets the whole store). The artifact carries the raw compliance rows
    with their tamper-evidence hash chain and surfaces the store's reconcile
    status so it attests whether the trail is intact. Declared before ``/{id}``
    so the literal segment isn't parsed as an audit-row id.
    """
    logger.debug("Building regulatory audit export for owner=%s", scope.owner_user_id)
    try:
        return await build_regulatory_audit_export(db, owner_user_id=scope.owner_user_id)
    except Exception as e:
        logger.error(f"Error building regulatory audit export: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=Audit_logsResponse)
async def get_audit_logs(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Get a single audit_logs by ID, scoped to the caller's tenant"""
    logger.debug(f"Fetching audit_logs with id: {id}, fields={fields}")

    service = Audit_logsService(db)
    try:
        result = await service.get_by_id(id, owner_user_id=scope.owner_user_id)
        if not result:
            logger.warning(f"Audit_logs with id {id} not found")
            raise HTTPException(status_code=404, detail="Audit_logs not found")

        return (await service.render_rows([result]))[0]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching audit_logs {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
# NOTE: This router is intentionally READ-ONLY (finding H3). The audit trail is a
# compliance log: the audit middleware (middlewares/audit.py::write_audit_log) is
# its SOLE writer. No create/update/delete/batch endpoint is exposed here — an
# actor must not be able to fabricate, edit, or delete their own audit history.