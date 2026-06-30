import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.saudi_vat import validate_saudi_vat
from services.suppliers import SuppliersService
from services.supplier_credit import CREDIT_NOTE, SupplierCreditError, SupplierCreditService
from dependencies.auth import get_admin_user, get_current_user
from dependencies.tenancy import TenantScope, get_owner_id, get_tenant_scope
from schemas.auth import UserResponse

# Imported so ``Base.metadata.create_all`` registers the supplier-credit ledger
# table (the vendor-return credit-note store, #224). noqa: only a registration side
# effect — the symbol is used via the service layer.
from models.supplier_credit_ledger import SupplierCreditLedger  # noqa: F401

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/suppliers", tags=["suppliers"])


# ---------- Pydantic Schemas ----------
class SuppliersData(BaseModel):
    """Entity data schema (for create/update)"""
    client_id: int = None
    name: str
    contact_person: str = None
    email: str = None
    phone: str = None
    address: str = None
    vat_number: str = None
    payment_terms: str = None
    is_active: bool = None

    @field_validator("vat_number")
    @classmethod
    def _check_vat(cls, v):
        return validate_saudi_vat(v)


class SuppliersUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    client_id: Optional[int] = None
    name: Optional[str] = None
    contact_person: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    vat_number: Optional[str] = None
    payment_terms: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("vat_number")
    @classmethod
    def _check_vat(cls, v):
        return validate_saudi_vat(v)


class SuppliersResponse(BaseModel):
    """Entity response schema"""
    id: int
    user_id: str
    client_id: Optional[int] = None
    name: str
    contact_person: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    vat_number: Optional[str] = None
    payment_terms: Optional[str] = None
    is_active: Optional[bool] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SuppliersListResponse(BaseModel):
    """List response schema"""
    items: List[SuppliersResponse]
    total: int
    skip: int
    limit: int


class SuppliersBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[SuppliersData]


class SuppliersBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: SuppliersUpdateData


class SuppliersBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[SuppliersBatchUpdateItem]


class SuppliersBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=SuppliersListResponse)
async def query_supplierss(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Query supplierss with filtering, sorting, and pagination (user can only see their own records)"""
    logger.debug(f"Querying supplierss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = SuppliersService(db)
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
        logger.debug(f"Found {result['total']} supplierss")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying supplierss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=SuppliersListResponse)
async def query_supplierss_all(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    # Query supplierss with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying supplierss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = SuppliersService(db)
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
        logger.debug(f"Found {result['total']} supplierss")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying supplierss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=SuppliersResponse)
async def get_suppliers(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Get a single suppliers by ID (user can only see their own records)"""
    logger.debug(f"Fetching suppliers with id: {id}, fields={fields}")
    
    service = SuppliersService(db)
    try:
        result = await service.get_by_id(id, user_id=scope.owner_user_id)
        if not result:
            logger.warning(f"Suppliers with id {id} not found")
            raise HTTPException(status_code=404, detail="Suppliers not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching suppliers {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


# ---------- Vendor returns / supplier credit notes (ISSUE-224, M4 Inventory) ----------
class VendorReturnLine(BaseModel):
    """One product line being returned to the vendor.

    ``cost`` is the per-unit credit value; it defaults to the product's
    ``cost_price`` so the credit note reflects real landed cost.
    """
    product_id: int
    quantity: int
    cost: Optional[float] = None


class VendorReturnRequest(BaseModel):
    """Return received goods to a supplier (#224).

    - ``lines`` — the ``{product_id, quantity, cost?}`` being returned.
    - ``branch_id`` — draw the stock back out of the per-branch ledger the POS
      deducts from (omit to fall back to the client-level aggregate ``products.quantity``).
    - ``purchase_order_id`` — optional link to the PO the goods were received on.
    """
    lines: List[VendorReturnLine]
    branch_id: Optional[int] = None
    purchase_order_id: Optional[int] = None
    note: Optional[str] = None


class VendorReturnResponse(BaseModel):
    supplier_id: int
    credit_note_id: int
    amount: float
    balance: float
    returned_items: int
    message: str


class SupplierCreditEntry(BaseModel):
    id: int
    entry_type: str
    amount: float
    balance_after: float
    purchase_order_id: Optional[int] = None
    note: Optional[str] = None


class SupplierCreditResponse(BaseModel):
    supplier_id: int
    balance: float
    history: List[SupplierCreditEntry]


async def _load_owned_supplier(db: AsyncSession, owner_id: str, supplier_id: int):
    """Fetch a supplier the caller owns, or raise 404 (SEC-02 tenancy gate)."""
    from sqlalchemy import select

    from models.suppliers import Suppliers

    supplier = (
        await db.execute(
            select(Suppliers).where(
                Suppliers.id == supplier_id, Suppliers.user_id == owner_id
            )
        )
    ).scalar_one_or_none()
    if not supplier:
        raise HTTPException(status_code=404, detail="Suppliers not found")
    return supplier


@router.post("/{id}/returns", response_model=VendorReturnResponse)
async def create_vendor_return(
    id: int,
    request: VendorReturnRequest = Body(...),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Return received goods to a supplier and post a supplier credit note (#224).

    Each line draws its quantity back out of stock — the per-branch ledger
    (``product_branch_stock``) when ``branch_id`` is given, otherwise the
    client-level aggregate ``products.quantity`` — and the combined value
    (``Σ quantity × cost``, cost defaulting to the product's ``cost_price``) is
    appended to the supplier-credit ledger as a single credit note. Returning more
    than is on hand at the location, or a non-positive quantity, is rejected (400)
    so stock can never be driven negative and an empty return cannot raise credit.
    """
    from sqlalchemy import select

    from models.products import Products

    supplier = await _load_owned_supplier(db, owner_id, id)

    # Collapse the request to a positive-quantity, per-product map (a product may
    # legitimately appear on more than one line).
    want: dict = {}
    cost_override: dict = {}
    for line in request.lines:
        if line.quantity is None or line.quantity <= 0:
            raise HTTPException(
                status_code=400,
                detail="Return quantity must be a positive number of units",
            )
        want[line.product_id] = want.get(line.product_id, 0) + int(line.quantity)
        if line.cost is not None:
            cost_override[line.product_id] = line.cost
    if not want:
        raise HTTPException(status_code=400, detail="Nothing to return")

    branch_id = request.branch_id
    client = None
    if branch_id is not None:
        from routers.pos import get_client_for_user

        client = await get_client_for_user(db, owner_id)

    # First pass: validate every line (ownership + sufficient on-hand) BEFORE
    # mutating any stock, so a partly-invalid return books nothing.
    products: dict = {}
    rows: dict = {}
    credit_amount = 0.0
    for pid, qty in want.items():
        product = (
            await db.execute(
                select(Products).where(
                    Products.id == pid, Products.user_id == owner_id
                )
            )
        ).scalar_one_or_none()
        if not product:
            raise HTTPException(status_code=404, detail=f"Product {pid} not found")
        products[pid] = product

        if branch_id is not None:
            from services.branch_stock import get_or_init_row

            row = await get_or_init_row(db, owner_id, client.id, branch_id, product)
            on_hand = row.quantity or 0
            rows[pid] = row
        else:
            on_hand = product.quantity or 0
        if qty > on_hand:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Cannot return {qty} unit(s) of product {pid}: only {on_hand} "
                    f"on hand"
                ),
            )

        unit_cost = cost_override.get(pid, product.cost_price)
        credit_amount += qty * float(unit_cost or 0)

    # Second pass: draw the stock back out.
    for pid, qty in want.items():
        if branch_id is not None:
            rows[pid].quantity = (rows[pid].quantity or 0) - qty
        else:
            products[pid].quantity = (products[pid].quantity or 0) - qty

    # Persist the stock decrements before the credit-note post (which commits).
    await db.flush()

    note = request.note or f"Vendor return ({len(want)} line(s))"
    service = SupplierCreditService(db)
    try:
        row = await service.post(
            id,
            user_id=owner_id,
            client_id=supplier.client_id,
            entry_type=CREDIT_NOTE,
            amount=credit_amount,
            note=note,
            purchase_order_id=request.purchase_order_id,
        )
    except SupplierCreditError as exc:
        # A zero-value return (all costs unknown/zero) cannot raise a credit note.
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))

    balance = await service.balance(id, user_id=owner_id)
    return VendorReturnResponse(
        supplier_id=id,
        credit_note_id=row.id,
        amount=float(row.amount),
        balance=float(balance),
        returned_items=len(want),
        message=note,
    )


@router.get("/{id}/credit", response_model=SupplierCreditResponse)
async def get_supplier_credit(
    id: int,
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """The supplier's outstanding credit balance and credit-note history (#224)."""
    await _load_owned_supplier(db, owner_id, id)
    service = SupplierCreditService(db)
    balance = await service.balance(id, user_id=owner_id)
    history = await service.history(id, user_id=owner_id)
    return SupplierCreditResponse(
        supplier_id=id,
        balance=float(balance),
        history=[
            SupplierCreditEntry(
                id=r.id,
                entry_type=r.entry_type,
                amount=float(r.amount),
                balance_after=float(r.balance_after),
                purchase_order_id=r.purchase_order_id,
                note=r.note,
            )
            for r in history
        ],
    )


@router.post("", response_model=SuppliersResponse, status_code=201)
async def create_suppliers(
    data: SuppliersData,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Create a new suppliers"""
    logger.debug(f"Creating new suppliers with data: {data}")
    
    service = SuppliersService(db)
    try:
        result = await service.create(data.model_dump(), user_id=(scope.owner_user_id or str(current_user.id)))
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create suppliers")
        
        logger.info(f"Suppliers created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating suppliers: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating suppliers: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[SuppliersResponse], status_code=201)
async def create_supplierss_batch(
    request: SuppliersBatchCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Create multiple supplierss in a single request"""
    logger.debug(f"Batch creating {len(request.items)} supplierss")
    
    service = SuppliersService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump(), user_id=(scope.owner_user_id or str(current_user.id)))
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} supplierss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[SuppliersResponse])
async def update_supplierss_batch(
    request: SuppliersBatchUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Update multiple supplierss in a single request (requires ownership)"""
    logger.debug(f"Batch updating {len(request.items)} supplierss")
    
    service = SuppliersService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict, user_id=scope.owner_user_id)
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} supplierss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=SuppliersResponse)
async def update_suppliers(
    id: int,
    data: SuppliersUpdateData,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing suppliers (requires ownership)"""
    logger.debug(f"Updating suppliers {id} with data: {data}")

    service = SuppliersService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict, user_id=scope.owner_user_id)
        if not result:
            logger.warning(f"Suppliers with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Suppliers not found")
        
        logger.info(f"Suppliers {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating suppliers {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating suppliers {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_supplierss_batch(
    request: SuppliersBatchDeleteRequest,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple supplierss by their IDs (requires ownership)"""
    logger.debug(f"Batch deleting {len(request.ids)} supplierss")
    
    service = SuppliersService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id, user_id=scope.owner_user_id)
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} supplierss successfully")
        return {"message": f"Successfully deleted {deleted_count} supplierss", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_suppliers(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Delete a single suppliers by ID (requires ownership)"""
    logger.debug(f"Deleting suppliers with id: {id}")
    
    service = SuppliersService(db)
    try:
        success = await service.delete(id, user_id=scope.owner_user_id)
        if not success:
            logger.warning(f"Suppliers with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Suppliers not found")
        
        logger.info(f"Suppliers {id} deleted successfully")
        return {"message": "Suppliers deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting suppliers {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")