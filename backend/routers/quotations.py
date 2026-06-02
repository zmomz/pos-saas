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


# ---------- Routes ----------
@router.get("", response_model=QuotationsListResponse)
async def query_quotationss(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
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
            user_id=str(current_user.id),
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
    db: AsyncSession = Depends(get_db),
):
    """Render a quotation as an **always-Arabic** print-ready document (SRS §7).

    Like the tax-invoice document, this is forced RTL/Arabic with Arabic-Indic
    numerals regardless of the caller's UI language. A quotation is *not* a fiscal
    document, so it carries no ZATCA QR or stamp.
    """
    service = QuotationsService(db)
    quote = await service.get_by_id(id, user_id=str(current_user.id))
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
    db: AsyncSession = Depends(get_db),
):
    """Get a single quotations by ID (user can only see their own records)"""
    logger.debug(f"Fetching quotations with id: {id}, fields={fields}")

    service = QuotationsService(db)
    try:
        result = await service.get_by_id(id, user_id=str(current_user.id))
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
    db: AsyncSession = Depends(get_db),
):
    """Create a new quotations"""
    logger.debug(f"Creating new quotations with data: {data}")

    service = QuotationsService(db)
    try:
        result = await service.create(
            _with_quote_number(data.model_dump()), user_id=str(current_user.id)
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


@router.post("/batch", response_model=List[QuotationsResponse], status_code=201)
async def create_quotationss_batch(
    request: QuotationsBatchCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create multiple quotationss in a single request"""
    logger.debug(f"Batch creating {len(request.items)} quotationss")

    service = QuotationsService(db)
    results = []

    try:
        for item_data in request.items:
            result = await service.create(
                _with_quote_number(item_data.model_dump()), user_id=str(current_user.id)
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
    db: AsyncSession = Depends(get_db),
):
    """Update multiple quotationss in a single request (requires ownership)"""
    logger.debug(f"Batch updating {len(request.items)} quotationss")

    service = QuotationsService(db)
    results = []

    try:
        for item in request.items:
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict, user_id=str(current_user.id))
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
    db: AsyncSession = Depends(get_db),
):
    """Update an existing quotations (requires ownership)"""
    logger.debug(f"Updating quotations {id} with data: {data}")

    service = QuotationsService(db)
    try:
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict, user_id=str(current_user.id))
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
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple quotationss by their IDs (requires ownership)"""
    logger.debug(f"Batch deleting {len(request.ids)} quotationss")

    service = QuotationsService(db)
    deleted_count = 0

    try:
        for item_id in request.ids:
            success = await service.delete(item_id, user_id=str(current_user.id))
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
    db: AsyncSession = Depends(get_db),
):
    """Delete a single quotations by ID (requires ownership)"""
    logger.debug(f"Deleting quotations with id: {id}")

    service = QuotationsService(db)
    try:
        success = await service.delete(id, user_id=str(current_user.id))
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
