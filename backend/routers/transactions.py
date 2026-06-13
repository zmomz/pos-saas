import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.transactions import TransactionsService
from dependencies.auth import get_admin_user, get_current_user
from dependencies.tenancy import TenantScope, get_tenant_scope
from schemas.auth import UserResponse

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/transactions", tags=["transactions"])


def _fiscal_record_locked() -> HTTPException:
    """C-6: transactions are sequenced, hashed, ZATCA-signed fiscal records.

    They may only be created/mutated through the atomic POS sale path
    (``/api/v1/pos``) and the refund/credit-note path — never via this generic
    CRUD triad, which would bypass inventory, the per-client counter, the hash
    chain and signing. Reads (list/get) remain owner-scoped and allowed.
    """
    return HTTPException(
        status_code=403,
        detail=(
            "Transactions are fiscal records and cannot be created, modified, or "
            "deleted directly. Use the POS sale (/api/v1/pos) and refund endpoints."
        ),
    )


# ---------- Pydantic Schemas ----------
class TransactionsData(BaseModel):
    """Entity data schema (for create/update)"""
    client_id: int
    invoice_number: str
    subtotal: float = None
    vat_amount: float = None
    discount_amount: float = None
    total_amount: float
    payment_method: str
    status: str = None
    zatca_qr: str = None
    zatca_hash: str = None
    items_json: str = None
    customer_name: str = None
    customer_phone: str = None


class TransactionsUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    client_id: Optional[int] = None
    invoice_number: Optional[str] = None
    subtotal: Optional[float] = None
    vat_amount: Optional[float] = None
    discount_amount: Optional[float] = None
    total_amount: Optional[float] = None
    payment_method: Optional[str] = None
    status: Optional[str] = None
    zatca_qr: Optional[str] = None
    zatca_hash: Optional[str] = None
    items_json: Optional[str] = None
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None


class TransactionsResponse(BaseModel):
    """Entity response schema"""
    id: int
    user_id: str
    client_id: int
    invoice_number: str
    subtotal: Optional[float] = None
    vat_amount: Optional[float] = None
    discount_amount: Optional[float] = None
    total_amount: float
    payment_method: str
    status: Optional[str] = None
    zatca_qr: Optional[str] = None
    zatca_hash: Optional[str] = None
    items_json: Optional[str] = None
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TransactionsListResponse(BaseModel):
    """List response schema"""
    items: List[TransactionsResponse]
    total: int
    skip: int
    limit: int


class TransactionsBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[TransactionsData]


class TransactionsBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: TransactionsUpdateData


class TransactionsBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[TransactionsBatchUpdateItem]


class TransactionsBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=TransactionsListResponse)
async def query_transactionss(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Query transactionss with filtering, sorting, and pagination (user can only see their own records)"""
    logger.debug(f"Querying transactionss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = TransactionsService(db)
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
        logger.debug(f"Found {result['total']} transactionss")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying transactionss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=TransactionsListResponse)
async def query_transactionss_all(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    # Query transactionss with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying transactionss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = TransactionsService(db)
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
        logger.debug(f"Found {result['total']} transactionss")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying transactionss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=TransactionsResponse)
async def get_transactions(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Get a single transactions by ID (user can only see their own records)"""
    logger.debug(f"Fetching transactions with id: {id}, fields={fields}")
    
    service = TransactionsService(db)
    try:
        result = await service.get_by_id(id, user_id=scope.owner_user_id)
        if not result:
            logger.warning(f"Transactions with id {id} not found")
            raise HTTPException(status_code=404, detail="Transactions not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching transactions {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=TransactionsResponse, status_code=201)
async def create_transactions(
    data: TransactionsData,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Disabled (C-6): create sales via the atomic POS endpoint instead."""
    raise _fiscal_record_locked()


@router.post("/batch", response_model=List[TransactionsResponse], status_code=201)
async def create_transactionss_batch(
    request: TransactionsBatchCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Disabled (C-6): create sales via the atomic POS endpoint instead."""
    raise _fiscal_record_locked()


@router.put("/batch", response_model=List[TransactionsResponse])
async def update_transactionss_batch(
    request: TransactionsBatchUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Disabled (C-6): fiscal records are immutable via this triad."""
    raise _fiscal_record_locked()


@router.put("/{id}", response_model=TransactionsResponse)
async def update_transactions(
    id: int,
    data: TransactionsUpdateData,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Disabled (C-6): fiscal records are immutable via this triad."""
    raise _fiscal_record_locked()


@router.delete("/batch")
async def delete_transactionss_batch(
    request: TransactionsBatchDeleteRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Disabled (C-6): fiscal records cannot be bulk-deleted via this triad."""
    raise _fiscal_record_locked()


@router.delete("/{id}")
async def delete_transactions(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Disabled (C-6): fiscal records cannot be deleted via this triad."""
    raise _fiscal_record_locked()