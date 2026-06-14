import json
import logging
from typing import List, Optional

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from models.clients import Clients
from services.production import PDFInvoiceService
from services.quotations import QuotationsService
from dependencies.auth import get_admin_user, get_current_user
from dependencies.tenancy import TenantScope, get_tenant_scope
from schemas.auth import UserResponse

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/quotations", tags=["quotations"])


# ---------- Pydantic Schemas ----------
class QuotationsData(BaseModel):
    """Entity data schema (for create/update)"""
    client_id: int = None
    quote_number: str = None
    customer_name: str = None
    customer_phone: str = None
    items_json: str = None
    subtotal: float = None
    vat_amount: float = None
    discount_amount: float = None
    total_amount: float = None
    valid_until: datetime = None
    status: str = None
    notes: str = None


class QuotationsUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    client_id: Optional[int] = None
    quote_number: Optional[str] = None
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    items_json: Optional[str] = None
    subtotal: Optional[float] = None
    vat_amount: Optional[float] = None
    discount_amount: Optional[float] = None
    total_amount: Optional[float] = None
    valid_until: Optional[datetime] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class QuotationsResponse(BaseModel):
    """Entity response schema"""
    id: int
    user_id: str
    client_id: Optional[int] = None
    quote_number: Optional[str] = None
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    items_json: Optional[str] = None
    subtotal: Optional[float] = None
    vat_amount: Optional[float] = None
    discount_amount: Optional[float] = None
    total_amount: Optional[float] = None
    valid_until: Optional[datetime] = None
    status: Optional[str] = None
    # ISSUE-056: the fiscal sale this quote was converted into (null until converted).
    converted_transaction_id: Optional[int] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class QuotationsListResponse(BaseModel):
    """List response schema"""
    items: List[QuotationsResponse]
    total: int
    skip: int
    limit: int


class QuotationsBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[QuotationsData]


class QuotationsBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: QuotationsUpdateData


class QuotationsBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[QuotationsBatchUpdateItem]


class QuotationsBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


def _with_quote_number(data: dict) -> dict:
    """Auto-assign a quote number when the caller doesn't supply one."""
    if not data.get("quote_number"):
        # Non-fiscal identifier — uniqueness-by-timestamp is sufficient (quotations
        # have no statutory sequential-counter requirement, unlike tax invoices).
        data["quote_number"] = f"QT-{int(datetime.now().timestamp())}"
    return data


# ---------- Status lifecycle (ISSUE-056) ----------
# A quotation moves forward through draft → sent → accepted and ends in one of two
# terminal states: ``converted`` (turned into a sale) or ``expired``. Transitions
# are forward-only and enforced server-side so a quote can't, e.g., be re-opened
# after it was converted. ``converted`` is reached ONLY via the convert endpoint.
_TERMINAL_STATUSES = {"converted", "expired"}
_ALLOWED_TRANSITIONS = {
    "draft": {"sent", "accepted", "expired"},
    "sent": {"accepted", "expired"},
    "accepted": {"expired"},
    "expired": set(),
    "converted": set(),
}


class QuotationStatusData(BaseModel):
    """Request body for an explicit status transition."""

    status: str


class QuotationConvertData(BaseModel):
    """Request body for converting a quotation into a sale.

    The pricing/lines come from the stored quotation; the caller only chooses how
    the resulting sale is paid (defaults to a single cash tender for the full
    total). Card-like tenders would need real capture, so the minimal slice settles
    cash — the sale still flows through the canonical ZATCA-stamping path.
    """

    payment_method: str = "cash"


class QuotationConvertResponse(BaseModel):
    """Outcome of a quote→sale conversion: the new fiscal sale + the quote status."""

    quotation_id: int
    status: str
    transaction_id: int
    invoice_number: str
    total_amount: float
    zatca_document_id: Optional[int] = None
    zatca_status: str


class _ConvertLine(BaseModel):
    """A quotation line normalized to the cart-line contract ``execute_sale`` expects
    (``model_dump()`` + ``product_id`` / ``quantity`` / ``variant_id``). An ad-hoc
    line with no catalog ``product_id`` still settles — the sale core skips inventory
    for an unknown product."""

    product_id: Optional[int] = None
    variant_id: Optional[int] = None
    name: Optional[str] = None
    name_ar: Optional[str] = None
    price: float = 0.0
    quantity: float = 1.0
    discount: float = 0.0


# ---------- Routes ----------
@router.get("", response_model=QuotationsListResponse)
async def query_quotationss(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Query quotationss with filtering, sorting, and pagination (user can only see their own records)"""
    logger.debug(f"Querying quotationss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = QuotationsService(db)
    try:
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
        logger.debug(f"Found {result['total']} quotationss")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying quotationss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=QuotationsListResponse)
async def query_quotationss_all(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    # Query quotationss with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying quotationss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = QuotationsService(db)
    try:
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
        logger.debug(f"Found {result['total']} quotationss")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying quotationss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}/document", response_class=HTMLResponse)
async def get_quotation_document(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Render a quotation as an **always-Arabic** print-ready document (SRS §7).

    Like the tax-invoice document, this is forced RTL/Arabic with Arabic-Indic
    numerals regardless of the caller's UI language. A quotation is *not* a fiscal
    document, so it carries no ZATCA QR or stamp.
    """
    service = QuotationsService(db)
    quote = await service.get_by_id(id, user_id=scope.owner_user_id)
    if not quote:
        raise HTTPException(status_code=404, detail="Quotation not found")

    try:
        line_items = json.loads(quote.items_json) if quote.items_json else []
    except (ValueError, TypeError):
        line_items = []

    # Best-effort seller info from the caller's tenancy client row, if any.
    seller_name, seller_vat = "Business", "000000000000000"
    cres = await db.execute(select(Clients).where(Clients.user_id == str(current_user.id)))
    merchant = cres.scalar_one_or_none()
    if merchant:
        seller_name = merchant.business_name or seller_name
        seller_vat = merchant.vat_number or seller_vat

    issue_date = quote.created_at.strftime("%Y-%m-%d %H:%M") if quote.created_at else ""
    valid_until = quote.valid_until.strftime("%Y-%m-%d") if quote.valid_until else ""

    html = PDFInvoiceService.generate_quotation_html(
        seller_name=seller_name,
        seller_vat=seller_vat,
        buyer_name=quote.customer_name or "عميل",  # "Customer" in Arabic
        quote_number=quote.quote_number or f"QT-{quote.id}",
        issue_date=issue_date,
        valid_until=valid_until,
        line_items=line_items,
        subtotal=quote.subtotal or 0,
        vat_amount=quote.vat_amount or 0,
        total_amount=quote.total_amount or 0,
        discount=quote.discount_amount or 0,
        notes=quote.notes or "",
    )
    return HTMLResponse(content=html)


@router.get("/{id}", response_model=QuotationsResponse)
async def get_quotations(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Get a single quotations by ID (user can only see their own records)"""
    logger.debug(f"Fetching quotations with id: {id}, fields={fields}")

    service = QuotationsService(db)
    try:
        result = await service.get_by_id(id, user_id=scope.owner_user_id)
        if not result:
            logger.warning(f"Quotations with id {id} not found")
            raise HTTPException(status_code=404, detail="Quotations not found")

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching quotations {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=QuotationsResponse, status_code=201)
async def create_quotations(
    data: QuotationsData,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Create a new quotations"""
    logger.debug(f"Creating new quotations with data: {data}")

    service = QuotationsService(db)
    try:
        result = await service.create(
            _with_quote_number(data.model_dump()), user_id=scope.owner_user_id
        )
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create quotations")

        logger.info(f"Quotations created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating quotations: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating quotations: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.put("/{id}/status", response_model=QuotationsResponse)
async def transition_quotation_status(
    id: int,
    data: QuotationStatusData,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Move a quotation along its lifecycle (ISSUE-056), enforcing valid transitions.

    Forward-only: draft → sent → accepted, with ``expired`` reachable from any
    non-terminal state. ``converted`` is terminal and is reached only via
    ``/convert``; it can't be set here. An illegal transition is a 400.
    """
    service = QuotationsService(db)
    quote = await service.get_by_id(id, user_id=scope.owner_user_id)
    if not quote:
        raise HTTPException(status_code=404, detail="Quotation not found")

    target = (data.status or "").strip()
    current = quote.status or "draft"
    if target == current:
        return quote
    if target == "converted":
        raise HTTPException(
            status_code=400,
            detail="Use POST /convert to convert a quotation into a sale",
        )
    if target not in _ALLOWED_TRANSITIONS.get(current, set()):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition quotation from '{current}' to '{target or '(empty)'}'",
        )

    result = await service.update(id, {"status": target}, user_id=scope.owner_user_id)
    return result


@router.post("/{id}/convert", response_model=QuotationConvertResponse)
async def convert_quotation_to_sale(
    id: int,
    data: QuotationConvertData,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Convert a quotation into a real sale through the canonical sale core (ISSUE-056).

    Carries the quote's stored lines and authoritative totals into
    ``services.sale_core.execute_sale`` — the exact atomic path the POS and the
    restaurant settle use — so the resulting invoice is ZATCA-stamped where the
    client has e-invoicing enabled. On success the quotation is marked ``converted``
    and linked to the resulting transaction; a converted/expired quote cannot be
    converted again.
    """
    from services.sale_core import NormalizedCart, execute_sale
    from services.system_settings import get_effective_tax_rate

    service = QuotationsService(db)
    quote = await service.get_by_id(id, user_id=scope.owner_user_id)
    if not quote:
        raise HTTPException(status_code=404, detail="Quotation not found")
    if (quote.status or "draft") in _TERMINAL_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Quotation is '{quote.status}' and cannot be converted",
        )

    client = (
        await db.execute(
            select(Clients).where(Clients.user_id == scope.owner_user_id)
        )
    ).scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=403, detail="Only clients can convert quotations")

    try:
        raw_lines = json.loads(quote.items_json) if quote.items_json else []
    except (ValueError, TypeError):
        raw_lines = []
    lines = [_ConvertLine(**{k: v for k, v in ln.items() if k in _ConvertLine.model_fields})
             for ln in raw_lines]
    if not lines:
        raise HTTPException(status_code=400, detail="Quotation has no line items to convert")

    subtotal = round(float(quote.subtotal or 0), 2)
    discount_amount = round(float(quote.discount_amount or 0), 2)
    vat_amount = round(float(quote.vat_amount or 0), 2)
    total_amount = round(float(quote.total_amount or 0), 2)
    vat_rate = await get_effective_tax_rate(db, 15.0)

    result = await execute_sale(
        db,
        NormalizedCart(
            user_id=scope.owner_user_id,
            client=client,
            lines=lines,
            subtotal=subtotal,
            discount_amount=discount_amount,
            vat_rate=vat_rate,
            vat_amount=vat_amount,
            total_amount=total_amount,
            tender_specs=[
                {"tender_type": data.payment_method or "cash", "amount": total_amount}
            ],
            payment_method=data.payment_method or "cash",
            customer_name=quote.customer_name,
            customer_phone=quote.customer_phone,
        ),
    )
    transaction = result.transaction

    # Link the sale and close the quote. execute_sale already committed the sale;
    # this records the conversion outcome on the quote in its own commit.
    await service.update(
        id,
        {"status": "converted", "converted_transaction_id": transaction.id},
        user_id=scope.owner_user_id,
    )

    return QuotationConvertResponse(
        quotation_id=quote.id,
        status="converted",
        transaction_id=transaction.id,
        invoice_number=transaction.invoice_number,
        total_amount=transaction.total_amount,
        zatca_document_id=result.document_id,
        zatca_status="signed" if result.document_id is not None else "disabled",
    )


@router.post("/batch", response_model=List[QuotationsResponse], status_code=201)
async def create_quotationss_batch(
    request: QuotationsBatchCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Create multiple quotationss in a single request"""
    logger.debug(f"Batch creating {len(request.items)} quotationss")

    service = QuotationsService(db)
    results = []

    try:
        for item_data in request.items:
            result = await service.create(
                _with_quote_number(item_data.model_dump()), user_id=scope.owner_user_id
            )
            if result:
                results.append(result)

        logger.info(f"Batch created {len(results)} quotationss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[QuotationsResponse])
async def update_quotationss_batch(
    request: QuotationsBatchUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Update multiple quotationss in a single request (requires ownership)"""
    logger.debug(f"Batch updating {len(request.items)} quotationss")

    service = QuotationsService(db)
    results = []

    try:
        for item in request.items:
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict, user_id=scope.owner_user_id)
            if result:
                results.append(result)

        logger.info(f"Batch updated {len(results)} quotationss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=QuotationsResponse)
async def update_quotations(
    id: int,
    data: QuotationsUpdateData,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing quotations (requires ownership)"""
    logger.debug(f"Updating quotations {id} with data: {data}")

    service = QuotationsService(db)
    try:
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict, user_id=scope.owner_user_id)
        if not result:
            logger.warning(f"Quotations with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Quotations not found")

        logger.info(f"Quotations {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating quotations {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating quotations {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_quotationss_batch(
    request: QuotationsBatchDeleteRequest,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple quotationss by their IDs (requires ownership)"""
    logger.debug(f"Batch deleting {len(request.ids)} quotationss")

    service = QuotationsService(db)
    deleted_count = 0

    try:
        for item_id in request.ids:
            success = await service.delete(item_id, user_id=scope.owner_user_id)
            if success:
                deleted_count += 1

        logger.info(f"Batch deleted {deleted_count} quotationss successfully")
        return {"message": f"Successfully deleted {deleted_count} quotationss", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_quotations(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Delete a single quotations by ID (requires ownership)"""
    logger.debug(f"Deleting quotations with id: {id}")

    service = QuotationsService(db)
    try:
        success = await service.delete(id, user_id=scope.owner_user_id)
        if not success:
            logger.warning(f"Quotations with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Quotations not found")

        logger.info(f"Quotations {id} deleted successfully")
        return {"message": "Quotations deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting quotations {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
