import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.customers import CustomersService
from dependencies.auth import get_admin_user, get_current_user
from dependencies.tenancy import TenantScope, get_tenant_scope
from models.audit_logs import Audit_logs
from models.transactions import Transactions
from schemas.auth import UserResponse

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/customers", tags=["customers"])


# ---------- Pydantic Schemas ----------
class CustomersData(BaseModel):
    """Entity data schema (for create/update)"""
    name: str
    phone: str = None
    email: str = None
    vat_number: str = None  # buyer VAT for B2B invoices (CRM-01)
    notes: str = None
    total_purchases: float = None
    visit_count: int = None
    marketing_consent: Optional[bool] = None  # PDPL opt-in (SEC-05 / CRM-05)


class CustomersUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    vat_number: Optional[str] = None  # buyer VAT for B2B invoices (CRM-01)
    notes: Optional[str] = None
    total_purchases: Optional[float] = None
    visit_count: Optional[int] = None
    marketing_consent: Optional[bool] = None  # PDPL opt-in (SEC-05 / CRM-05)


class CustomersResponse(BaseModel):
    """Entity response schema"""
    id: int
    user_id: str
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    vat_number: Optional[str] = None
    notes: Optional[str] = None
    total_purchases: Optional[float] = None
    visit_count: Optional[int] = None
    marketing_consent: Optional[bool] = None
    consent_updated_at: Optional[datetime] = None
    pii_erased_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CustomersListResponse(BaseModel):
    """List response schema"""
    items: List[CustomersResponse]
    total: int
    skip: int
    limit: int


class CustomersBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[CustomersData]


class CustomersBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: CustomersUpdateData


class CustomersBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[CustomersBatchUpdateItem]


class CustomersBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=CustomersListResponse)
async def query_customerss(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Query customerss with filtering, sorting, and pagination (user can only see their own records)"""
    logger.debug(f"Querying customerss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = CustomersService(db)
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
        logger.debug(f"Found {result['total']} customerss")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying customerss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=CustomersListResponse)
async def query_customerss_all(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    # Query customerss with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying customerss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = CustomersService(db)
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
        logger.debug(f"Found {result['total']} customerss")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying customerss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=CustomersResponse)
async def get_customers(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Get a single customers by ID (user can only see their own records)"""
    logger.debug(f"Fetching customers with id: {id}, fields={fields}")
    
    service = CustomersService(db)
    try:
        result = await service.get_by_id(id, user_id=scope.owner_user_id)
        if not result:
            logger.warning(f"Customers with id {id} not found")
            raise HTTPException(status_code=404, detail="Customers not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching customers {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


# ---------- PDPL data-subject rights (SEC-05 / F-050) ----------
class DataSubjectTransaction(BaseModel):
    """A fiscal record linked to the data subject (read-only, retained)."""
    id: int
    invoice_number: str
    total_amount: Optional[float] = None
    status: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CustomerDataExportResponse(BaseModel):
    """PDPL right-to-access / portability bundle for one customer."""
    customer: CustomersResponse
    transactions: List[DataSubjectTransaction]
    transaction_count: int
    # Why some PII (buyer name/phone/VAT on invoices) is retained even after an
    # erasure request — ZATCA's 6-year fiscal-retention obligation overrides
    # erasure for fiscal records (a lawful-basis exemption under PDPL).
    retention_notice: str


def _linked_transactions_filter(customer):
    """Match the customer's fiscal rows by the PII denormalized onto a sale.

    Sales copy ``customer_name``/``customer_phone`` at ring-up time (there is no
    customer FK on ``transactions``). Phone is the most reliable identifier; fall
    back to name. After erasure both are cleared so nothing links back.
    """
    conditions = []
    if customer.phone:
        conditions.append(Transactions.customer_phone == customer.phone)
    if customer.name:
        conditions.append(Transactions.customer_name == customer.name)
    return conditions


@router.get("/{id}/data-export", response_model=CustomerDataExportResponse)
async def export_customer_data(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """PDPL (SEC-05) data-subject access/portability: export everything held about
    one customer — their CRM record plus every fiscal transaction linked to them.

    Owner-scoped: the merchant can only export a customer in their own scope
    (a foreign/unknown id → 404, SEC-02).
    """
    logger.debug(f"PDPL data export for customer {id}")
    service = CustomersService(db)
    try:
        customer = await service.get_by_id(id, user_id=scope.owner_user_id)
        if not customer:
            raise HTTPException(status_code=404, detail="Customers not found")

        conditions = _linked_transactions_filter(customer)
        transactions = []
        if conditions:
            result = await db.execute(
                select(Transactions)
                .where(
                    Transactions.user_id == scope.owner_user_id,
                    or_(*conditions),
                )
                .order_by(Transactions.id.desc())
            )
            transactions = result.scalars().all()

        return {
            "customer": customer,
            "transactions": transactions,
            "transaction_count": len(transactions),
            "retention_notice": (
                "Fiscal records (invoices/credit notes) are retained for 6 years "
                "under ZATCA tax law and are not erased by a data-subject request."
            ),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting customer {id} data: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/{id}/erase", response_model=CustomersResponse)
async def erase_customer_pii(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """PDPL (SEC-05) right-to-erasure: tombstone a customer's personal data.

    Nulls the PII fields (phone/email/VAT/notes), tombstones the name, withdraws
    marketing consent and stamps ``pii_erased_at``. The row is retained (not hard
    deleted) so retained fiscal transactions stay referentially intact; those
    fiscal records keep their own buyer block under the ZATCA-retention exemption.
    The action is audited (SEC-07). Owner-scoped (a foreign/unknown id → 404).
    Idempotent — erasing an already-erased customer is a no-op that still 200s.
    """
    logger.debug(f"PDPL erasure for customer {id}")
    service = CustomersService(db)
    try:
        customer = await service.get_by_id(id, user_id=scope.owner_user_id)
        if not customer:
            raise HTTPException(status_code=404, detail="Customers not found")

        # ``name`` is NOT NULL — tombstone it rather than null it.
        customer.name = "[erased]"
        customer.phone = None
        customer.email = None
        customer.vat_number = None
        customer.notes = None
        customer.marketing_consent = False
        now = datetime.now()
        customer.consent_updated_at = now
        customer.pii_erased_at = now

        db.add(
            Audit_logs(
                user_id=str(current_user.id),
                action="PDPL_ERASE_CUSTOMER",
                entity_type="customers",
                entity_id=str(customer.id),
                details=f"Erased PII for customer {customer.id} (PDPL right-to-erasure)",
            )
        )

        await db.commit()
        await db.refresh(customer)
        logger.info(f"Customer {id} PII erased (PDPL)")
        return customer
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error erasing customer {id} PII: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=CustomersResponse, status_code=201)
async def create_customers(
    data: CustomersData,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Create a new customers"""
    logger.debug(f"Creating new customers with data: {data}")
    
    service = CustomersService(db)
    try:
        create_dict = data.model_dump()
        # PDPL (SEC-05): stamp when consent was first recorded so the merchant can
        # evidence the opt-in.
        if create_dict.get("marketing_consent") is not None:
            create_dict["consent_updated_at"] = datetime.now()
        result = await service.create(create_dict, user_id=(scope.owner_user_id or str(current_user.id)))
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create customers")
        
        logger.info(f"Customers created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating customers: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating customers: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[CustomersResponse], status_code=201)
async def create_customerss_batch(
    request: CustomersBatchCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Create multiple customerss in a single request"""
    logger.debug(f"Batch creating {len(request.items)} customerss")
    
    service = CustomersService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump(), user_id=(scope.owner_user_id or str(current_user.id)))
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} customerss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[CustomersResponse])
async def update_customerss_batch(
    request: CustomersBatchUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Update multiple customerss in a single request (requires ownership)"""
    logger.debug(f"Batch updating {len(request.items)} customerss")
    
    service = CustomersService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict, user_id=scope.owner_user_id)
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} customerss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=CustomersResponse)
async def update_customers(
    id: int,
    data: CustomersUpdateData,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing customers (requires ownership)"""
    logger.debug(f"Updating customers {id} with data: {data}")

    service = CustomersService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        # PDPL (SEC-05): re-stamp whenever the consent flag is changed (given or
        # withdrawn) so the merchant can evidence the change.
        if "marketing_consent" in update_dict:
            update_dict["consent_updated_at"] = datetime.now()
        result = await service.update(id, update_dict, user_id=scope.owner_user_id)
        if not result:
            logger.warning(f"Customers with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Customers not found")
        
        logger.info(f"Customers {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating customers {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating customers {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_customerss_batch(
    request: CustomersBatchDeleteRequest,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple customerss by their IDs (requires ownership)"""
    logger.debug(f"Batch deleting {len(request.ids)} customerss")
    
    service = CustomersService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id, user_id=scope.owner_user_id)
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} customerss successfully")
        return {"message": f"Successfully deleted {deleted_count} customerss", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_customers(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Delete a single customers by ID (requires ownership)"""
    logger.debug(f"Deleting customers with id: {id}")
    
    service = CustomersService(db)
    try:
        success = await service.delete(id, user_id=scope.owner_user_id)
        if not success:
            logger.warning(f"Customers with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Customers not found")
        
        logger.info(f"Customers {id} deleted successfully")
        return {"message": "Customers deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting customers {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")