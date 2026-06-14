"""Restaurant operations router — floor map, tables, order tickets (F-045 / RST-01..03).

The first slice of the "unified retail + restaurant" vision (CLAUDE.md). Mounts at
``/api/v1/restaurant`` and is **double-gated** exactly as INTENDED_BEHAVIOR.md §4.5
specifies:

1. ``business_type`` of the caller's client must be ``restaurant`` or ``both`` — a
   retail-only merchant gets 403 (the discriminator added with this finding), and
2. the per-client ``restaurant`` feature flag must not be disabled
   (``require_feature`` semantics — enabled by default).

A non-client account (master/agent/unknown) gets 403. Every read/write is scoped
to the caller's ``user_id`` in the service layer so one client can never see
another's floor (SEC-02).
"""
import asyncio
import json
import logging
from typing import Any, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import AccessTokenError, decode_access_token
from core.database import db_manager, get_db
from dependencies.auth import get_current_user
from dependencies.features import is_feature_enabled
from models.clients import Clients
from schemas.auth import UserResponse
from services import zatca as zatca_service_mod
from services import zatca_sale
from services.escpos import build_kot_base64, build_receipt_base64
from services.kds_channel import kds_broker
from services.restaurant import (
    KDS_STATUSES,
    ORDER_TYPES,
    SPLIT_STRATEGIES,
    TABLE_STATES,
    RestaurantService,
)
from services.system_settings import get_effective_tax_rate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/restaurant", tags=["restaurant"])

# business_type values that unlock the restaurant vertical.
RESTAURANT_BUSINESS_TYPES = ("restaurant", "both")


# ---------- Gate dependency ----------
async def _resolve_restaurant_client(db: AsyncSession, user_id: str) -> Clients:
    """Resolve a user's client row and enforce the two restaurant gates.

    Shared by the header-auth dependency and the SSE stream's query-token path so
    the double-gate (business_type ∈ restaurant/both + the ``restaurant`` feature
    flag) is identical everywhere. Raises 403 when any gate fails.
    """
    result = await db.execute(select(Clients).where(Clients.user_id == str(user_id)))
    client = result.scalar_one_or_none()
    if client is None:
        raise HTTPException(
            status_code=403, detail="Only client merchants can use restaurant features"
        )
    if (client.business_type or "retail") not in RESTAURANT_BUSINESS_TYPES:
        raise HTTPException(
            status_code=403,
            detail="Restaurant features require a 'restaurant' or 'both' business type",
        )
    if not await is_feature_enabled(db, client.id, "restaurant"):
        raise HTTPException(
            status_code=403, detail="The 'restaurant' feature is disabled for your account."
        )
    return client


async def get_restaurant_client(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Clients:
    """Resolve the caller's client row and enforce the two restaurant gates.

    Returns the ``Clients`` row (used for ``user_id`` scoping + ``client_id`` on
    created rows). Raises 403 when the caller is not a client, when their
    ``business_type`` isn't restaurant/both, or when the ``restaurant`` feature is
    disabled for them.
    """
    return await _resolve_restaurant_client(db, current_user.id)


# ---------- Pydantic Schemas ----------
class ZoneData(BaseModel):
    name: str
    branch_id: Optional[int] = None


class ZoneUpdateData(BaseModel):
    name: Optional[str] = None
    branch_id: Optional[int] = None


class ZoneResponse(BaseModel):
    id: int
    user_id: str
    client_id: Optional[int] = None
    branch_id: Optional[int] = None
    name: str

    class Config:
        from_attributes = True


class TableData(BaseModel):
    name: str
    seats: Optional[int] = 4
    zone_id: Optional[int] = None
    branch_id: Optional[int] = None


class TableUpdateData(BaseModel):
    name: Optional[str] = None
    seats: Optional[int] = None
    zone_id: Optional[int] = None
    branch_id: Optional[int] = None
    state: Optional[str] = None


class TableResponse(BaseModel):
    id: int
    user_id: str
    client_id: Optional[int] = None
    branch_id: Optional[int] = None
    zone_id: Optional[int] = None
    name: str
    seats: Optional[int] = None
    state: Optional[str] = None
    current_ticket_id: Optional[int] = None

    class Config:
        from_attributes = True


class TableListResponse(BaseModel):
    items: List[TableResponse]
    total: int


class OpenOrderRequest(BaseModel):
    order_type: Optional[str] = "dine_in"
    customer_name: Optional[str] = None
    party_size: Optional[int] = None
    notes: Optional[str] = None


class CreateTicketRequest(BaseModel):
    """Open an order ticket whose flow is driven by ``order_type`` (F-058).

    ``dine_in`` requires ``table_id`` (the table flips to occupied);
    ``takeaway`` / ``delivery`` are tableless and ignore ``table_id``.
    """

    order_type: Optional[str] = "dine_in"
    table_id: Optional[int] = None
    branch_id: Optional[int] = None
    customer_name: Optional[str] = None
    party_size: Optional[int] = None
    notes: Optional[str] = None


class OrderTicketResponse(BaseModel):
    id: int
    user_id: str
    client_id: Optional[int] = None
    branch_id: Optional[int] = None
    table_id: Optional[int] = None
    order_type: Optional[str] = None
    status: Optional[str] = None
    customer_name: Optional[str] = None
    party_size: Optional[int] = None
    notes: Optional[str] = None
    # Optional service-charge % applied to the bill, outside the VAT base (F-061).
    service_charge_pct: Optional[float] = None

    class Config:
        from_attributes = True


class OrderTicketListResponse(BaseModel):
    items: List[OrderTicketResponse]
    total: int


# ---------- Order ticket line-item schemas (F-055) ----------
class TicketItemData(BaseModel):
    product_id: Optional[int] = None
    combo_id: Optional[int] = None
    variant_id: Optional[int] = None
    name: Optional[str] = None
    qty: float = 1
    unit_price: Optional[float] = None
    course: Optional[str] = "mains"
    seat_no: Optional[int] = None
    notes: Optional[str] = None
    prep_station_id: Optional[int] = None
    # A list of selected modifier ids (or dicts carrying ``id``); F-056 resolves,
    # validates required groups, prices the deltas, and serializes the selection.
    modifiers: Optional[Any] = None


class TicketItemUpdateData(BaseModel):
    qty: Optional[float] = None
    unit_price: Optional[float] = None
    name: Optional[str] = None
    course: Optional[str] = None
    seat_no: Optional[int] = None
    notes: Optional[str] = None


class TicketItemResponse(BaseModel):
    id: int
    user_id: str
    client_id: Optional[int] = None
    ticket_id: int
    product_id: Optional[int] = None
    variant_id: Optional[int] = None
    name: Optional[str] = None
    qty: float
    unit_price: float
    line_total: float
    course: Optional[str] = None
    seat_no: Optional[int] = None
    fire_state: Optional[str] = None
    prep_station_id: Optional[int] = None
    notes: Optional[str] = None
    modifiers: Optional[str] = None

    class Config:
        from_attributes = True


class TicketItemListResponse(BaseModel):
    items: List[TicketItemResponse]
    total: int


class FireCourseRequest(BaseModel):
    course: str


class TransferRequest(BaseModel):
    target_table_id: int


class MergeRequest(BaseModel):
    source_ticket_id: int


class SplitRequest(BaseModel):
    strategy: str
    n_ways: Optional[int] = None


class ServiceChargeRequest(BaseModel):
    """Apply (or clear) an optional service-charge % on a ticket (F-061)."""

    service_charge_pct: float = 0


# ---------- Check + settle schemas (F-059) ----------
class CheckRequest(BaseModel):
    """Print a non-fiscal proforma check for a ticket (F-059)."""

    tip_amount: float = 0


class SettlePayment(BaseModel):
    """One tender leg of a (possibly split) settlement, mirroring the POS payment."""

    method: str  # cash / card / mada / applepay / stcpay / tabby / tamara / giftcard…
    amount: float
    tender_type: Optional[str] = None
    token: Optional[str] = None
    simulate: Optional[str] = None  # sandbox-only: "approve" / "decline"
    terminal_id: Optional[int] = None
    gift_card_code: Optional[str] = None


class SettleRequest(BaseModel):
    """Settle a ticket into a real ZATCA invoice via the shared sale core (F-059).

    The tenders must cover the ticket's full ``amount_due`` (goods + VAT + service
    charge + tip). Provide ``payments`` for a split settlement, or leave it unset
    for a single-tender settlement driven by ``payment_method`` (+ the optional
    single-tender capture hints).
    """

    payment_method: str = "cash"
    payments: Optional[List[SettlePayment]] = None
    tip_amount: float = 0
    customer_name: Optional[str] = None
    customer_vat_number: Optional[str] = None
    allow_negative_stock: bool = False
    payment_token: Optional[str] = None
    payment_simulate: Optional[str] = None
    payment_terminal_id: Optional[int] = None
    payment_gift_card_code: Optional[str] = None


class SettleResponse(BaseModel):
    ticket_id: int
    transaction_id: int
    invoice_number: str
    subtotal: float
    vat_amount: float
    total_amount: float
    service_charge: float
    tip_amount: float
    amount_due: float
    # Fiscal linkage (null when the client has ZATCA disabled, ZA-09).
    zatca_document_id: Optional[int] = None
    zatca_status: str
    zatca_qr: Optional[str] = None
    zatca_qr_base64: Optional[str] = None
    # Always-Arabic 80mm receipt for the settled invoice (base64 ESC/POS).
    receipt_base64: Optional[str] = None
    ticket_status: str = "settled"
    table_freed: bool = False


# ---------- Modifier group / modifier / combo schemas (F-056) ----------
class ModifierGroupData(BaseModel):
    name: str
    name_ar: Optional[str] = None
    required: bool = False
    min_select: int = 0
    max_select: Optional[int] = 1


class ModifierGroupUpdateData(BaseModel):
    name: Optional[str] = None
    name_ar: Optional[str] = None
    required: Optional[bool] = None
    min_select: Optional[int] = None
    max_select: Optional[int] = None


class ModifierGroupResponse(BaseModel):
    id: int
    user_id: str
    client_id: Optional[int] = None
    name: str
    name_ar: Optional[str] = None
    required: Optional[bool] = None
    min_select: Optional[int] = None
    max_select: Optional[int] = None

    class Config:
        from_attributes = True


class ModifierData(BaseModel):
    name: str
    name_ar: Optional[str] = None
    price_delta: float = 0


class ModifierUpdateData(BaseModel):
    name: Optional[str] = None
    name_ar: Optional[str] = None
    price_delta: Optional[float] = None


class ModifierResponse(BaseModel):
    id: int
    user_id: str
    client_id: Optional[int] = None
    group_id: int
    name: str
    name_ar: Optional[str] = None
    price_delta: float

    class Config:
        from_attributes = True


class ComboComponent(BaseModel):
    product_id: int
    qty: float = 1


class ComboData(BaseModel):
    name: str
    name_ar: Optional[str] = None
    bundle_price: float = 0
    components: List[ComboComponent] = []
    is_active: bool = True


class ComboUpdateData(BaseModel):
    name: Optional[str] = None
    name_ar: Optional[str] = None
    bundle_price: Optional[float] = None
    components: Optional[List[ComboComponent]] = None
    is_active: Optional[bool] = None


class ComboResponse(BaseModel):
    id: int
    user_id: str
    client_id: Optional[int] = None
    name: str
    name_ar: Optional[str] = None
    bundle_price: float
    components: List[ComboComponent] = []
    component_sum: Optional[float] = None
    is_active: Optional[bool] = None

    class Config:
        from_attributes = True


# ---------- Bill-of-materials schemas (F-062) ----------
class BomEntryData(BaseModel):
    component_product_id: int
    qty_per: float = 1


class BomEntryUpdateData(BaseModel):
    qty_per: Optional[float] = None


class BomEntryResponse(BaseModel):
    id: int
    user_id: str
    client_id: Optional[int] = None
    parent_product_id: int
    component_product_id: int
    qty_per: float

    class Config:
        from_attributes = True


class BomListResponse(BaseModel):
    items: List[BomEntryResponse]
    total: int
    # Component costs rolled up to a parent cost-of-goods value (F-062 hook).
    cost_of_goods: float


# ---------- Prep-station / KDS schemas (F-057) ----------
class PrepStationData(BaseModel):
    name: str
    name_ar: Optional[str] = None
    sort_order: int = 0


class PrepStationUpdateData(BaseModel):
    name: Optional[str] = None
    name_ar: Optional[str] = None
    sort_order: Optional[int] = None


class PrepStationResponse(BaseModel):
    id: int
    user_id: str
    client_id: Optional[int] = None
    name: str
    name_ar: Optional[str] = None
    sort_order: Optional[int] = None

    class Config:
        from_attributes = True


# ---------- Zone routes ----------
@router.get("/zones", response_model=List[ZoneResponse])
async def list_zones(
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """List the caller's floor zones (RST-01)."""
    logger.debug(f"Listing floor zones for client {client.id}")
    service = RestaurantService(db)
    return await service.list_zones(user_id=client.user_id)


@router.post("/zones", response_model=ZoneResponse, status_code=201)
async def create_zone(
    data: ZoneData,
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """Create a floor zone (RST-01)."""
    logger.debug(f"Creating floor zone for client {client.id}: {data}")
    service = RestaurantService(db)
    try:
        return await service.create_zone(data.model_dump(), user_id=client.user_id, client_id=client.id)
    except Exception as e:
        logger.error(f"Error creating floor zone: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.put("/zones/{zone_id}", response_model=ZoneResponse)
async def update_zone(
    zone_id: int,
    data: ZoneUpdateData,
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """Update a floor zone (requires ownership)."""
    service = RestaurantService(db)
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    result = await service.update_zone(zone_id, updates, user_id=client.user_id)
    if not result:
        raise HTTPException(status_code=404, detail="Floor zone not found")
    return result


@router.delete("/zones/{zone_id}")
async def delete_zone(
    zone_id: int,
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """Delete a floor zone (requires ownership)."""
    service = RestaurantService(db)
    ok = await service.delete_zone(zone_id, user_id=client.user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Floor zone not found")
    return {"message": "Floor zone deleted successfully", "id": zone_id}


# ---------- Table routes ----------
@router.get("/tables", response_model=TableListResponse)
async def list_tables(
    zone_id: Optional[int] = Query(None),
    branch_id: Optional[int] = Query(None),
    state: Optional[str] = Query(None),
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """List the caller's tables, optionally filtered by zone/branch/state (RST-01)."""
    logger.debug(f"Listing tables for client {client.id} zone={zone_id} state={state}")
    service = RestaurantService(db)
    items = await service.list_tables(
        user_id=client.user_id, zone_id=zone_id, branch_id=branch_id, state=state
    )
    return {"items": items, "total": len(items)}


@router.get("/tables/{table_id}", response_model=TableResponse)
async def get_table(
    table_id: int,
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """Get a single table (requires ownership)."""
    service = RestaurantService(db)
    table = await service.get_table(table_id, user_id=client.user_id)
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")
    return table


@router.post("/tables", response_model=TableResponse, status_code=201)
async def create_table(
    data: TableData,
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """Place a new table on the floor (RST-01)."""
    logger.debug(f"Creating table for client {client.id}: {data}")
    service = RestaurantService(db)
    try:
        return await service.create_table(data.model_dump(), user_id=client.user_id, client_id=client.id)
    except Exception as e:
        logger.error(f"Error creating table: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.put("/tables/{table_id}", response_model=TableResponse)
async def update_table(
    table_id: int,
    data: TableUpdateData,
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """Update a table (name/seats/zone/branch) or transition its state (RST-01)."""
    service = RestaurantService(db)
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    if "state" in updates and updates["state"] not in TABLE_STATES:
        raise HTTPException(
            status_code=400, detail=f"Invalid state. Allowed: {', '.join(TABLE_STATES)}"
        )
    result = await service.update_table(table_id, updates, user_id=client.user_id)
    if not result:
        raise HTTPException(status_code=404, detail="Table not found")
    return result


@router.delete("/tables/{table_id}")
async def delete_table(
    table_id: int,
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """Delete a table (requires ownership)."""
    service = RestaurantService(db)
    ok = await service.delete_table(table_id, user_id=client.user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Table not found")
    return {"message": "Table deleted successfully", "id": table_id}


@router.post("/tables/{table_id}/open-order", response_model=OrderTicketResponse, status_code=201)
async def open_order(
    table_id: int,
    data: OpenOrderRequest,
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """Open an order ticket against a free table, flipping it to occupied (RST-02/03)."""
    logger.debug(f"Opening order on table {table_id} for client {client.id}")
    if data.order_type and data.order_type not in ORDER_TYPES:
        raise HTTPException(
            status_code=400, detail=f"Invalid order_type. Allowed: {', '.join(ORDER_TYPES)}"
        )
    service = RestaurantService(db)
    try:
        ticket = await service.open_order(
            table_id, data.model_dump(), user_id=client.user_id, client_id=client.id
        )
    except ValueError as e:
        # Table already occupied — can't double-seat it.
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.error(f"Error opening order on table {table_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    if ticket is None:
        raise HTTPException(status_code=404, detail="Table not found")
    return ticket


# ---------- Order ticket routes ----------
@router.get("/order-tickets", response_model=OrderTicketListResponse)
async def list_order_tickets(
    status: Optional[str] = Query(None),
    table_id: Optional[int] = Query(None),
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """List the caller's order tickets, optionally filtered by status/table (RST-02/03)."""
    service = RestaurantService(db)
    items = await service.list_tickets(user_id=client.user_id, status=status, table_id=table_id)
    return {"items": items, "total": len(items)}


@router.post("/order-tickets", response_model=OrderTicketResponse, status_code=201)
async def create_order_ticket(
    data: CreateTicketRequest,
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """Open an order ticket — ``order_type`` drives the flow (F-058).

    Dine-in requires a table (and occupies it); takeaway/delivery are tableless.
    """
    logger.debug(f"Creating {data.order_type} ticket for client {client.id}")
    if data.order_type and data.order_type not in ORDER_TYPES:
        raise HTTPException(
            status_code=400, detail=f"Invalid order_type. Allowed: {', '.join(ORDER_TYPES)}"
        )
    service = RestaurantService(db)
    try:
        ticket = await service.create_ticket(
            data.model_dump(), user_id=client.user_id, client_id=client.id
        )
    except ValueError as e:
        # Dine-in with no table, or a dine-in table already occupied.
        detail = str(e)
        status = 409 if "occupied" in detail.lower() else 400
        raise HTTPException(status_code=status, detail=detail)
    except Exception as e:
        logger.error(f"Error creating order ticket: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    if ticket is None:
        raise HTTPException(status_code=404, detail="Table not found")
    return ticket


@router.get("/order-tickets/{ticket_id}", response_model=OrderTicketResponse)
async def get_order_ticket(
    ticket_id: int,
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """Get a single order ticket (requires ownership)."""
    service = RestaurantService(db)
    ticket = await service.get_ticket(ticket_id, user_id=client.user_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Order ticket not found")
    return ticket


@router.get("/order-tickets/{ticket_id}/print-routing")
async def get_print_routing(
    ticket_id: int,
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """Where this ticket's documents print, driven by ``order_type`` (F-058)."""
    service = RestaurantService(db)
    ticket = await service.get_ticket(ticket_id, user_id=client.user_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Order ticket not found")
    return service.print_routing(ticket)


# ---------- Order ticket line items (F-055) ----------
@router.get("/order-tickets/{ticket_id}/items", response_model=TicketItemListResponse)
async def list_ticket_items(
    ticket_id: int,
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """List a ticket's line items (owner-scoped, RST-02)."""
    service = RestaurantService(db)
    ticket = await service.get_ticket(ticket_id, user_id=client.user_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Order ticket not found")
    items = await service.list_items(ticket_id, user_id=client.user_id)
    return {"items": items, "total": len(items)}


@router.post("/order-tickets/{ticket_id}/items", response_model=TicketItemResponse, status_code=201)
async def add_ticket_item(
    ticket_id: int,
    data: TicketItemData,
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """Add a menu item to an open ticket — qty/course/seat/note (RST-02)."""
    logger.debug(f"Adding line to ticket {ticket_id} for client {client.id}")
    service = RestaurantService(db)
    try:
        item = await service.add_item(
            ticket_id, data.model_dump(), user_id=client.user_id, client_id=client.id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error adding line to ticket {ticket_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    if item is None:
        raise HTTPException(status_code=404, detail="Order ticket not found")
    return item


@router.put("/order-tickets/{ticket_id}/items/{item_id}", response_model=TicketItemResponse)
async def update_ticket_item(
    ticket_id: int,
    item_id: int,
    data: TicketItemUpdateData,
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """Edit an *open* line's qty/course/seat/notes (RST-02)."""
    service = RestaurantService(db)
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    try:
        item = await service.update_item(ticket_id, item_id, updates, user_id=client.user_id)
    except ValueError as e:
        # Fired line — can't be silently re-priced.
        raise HTTPException(status_code=409, detail=str(e))
    if item is None:
        raise HTTPException(status_code=404, detail="Line item not found")
    return item


@router.delete("/order-tickets/{ticket_id}/items/{item_id}")
async def void_ticket_item(
    ticket_id: int,
    item_id: int,
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """Remove an *open* line; a fired line can't be silently deleted (RST-02)."""
    service = RestaurantService(db)
    try:
        ok = await service.void_item(ticket_id, item_id, user_id=client.user_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if ok is None:
        raise HTTPException(status_code=404, detail="Line item not found")
    return {"message": "Line item removed", "id": item_id}


@router.post("/order-tickets/{ticket_id}/fire")
async def fire_course(
    ticket_id: int,
    data: FireCourseRequest,
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """Fire a course to the kitchen — open lines of that course go fired (RST-02)."""
    service = RestaurantService(db)
    try:
        result = await service.fire_course(ticket_id, data.course, user_id=client.user_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if result is None:
        raise HTTPException(status_code=404, detail="Order ticket not found")
    return result


@router.post("/order-tickets/{ticket_id}/transfer", response_model=OrderTicketResponse)
async def transfer_ticket(
    ticket_id: int,
    data: TransferRequest,
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """Transfer a ticket (and its lines) to another table (RST-02)."""
    service = RestaurantService(db)
    try:
        ticket = await service.transfer_ticket(ticket_id, data.target_table_id, user_id=client.user_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if ticket is None:
        raise HTTPException(status_code=404, detail="Order ticket not found")
    return ticket


@router.post("/order-tickets/{ticket_id}/merge", response_model=OrderTicketResponse)
async def merge_tickets(
    ticket_id: int,
    data: MergeRequest,
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """Merge another ticket into this one, producing a single bill (RST-02)."""
    service = RestaurantService(db)
    try:
        ticket = await service.merge_tickets(ticket_id, data.source_ticket_id, user_id=client.user_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if ticket is None:
        raise HTTPException(status_code=404, detail="Order ticket not found")
    return ticket


@router.post("/order-tickets/{ticket_id}/split")
async def split_ticket(
    ticket_id: int,
    data: SplitRequest,
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """Compute the shares a bill splits into — by seat, amount, or item (RST-02)."""
    if data.strategy not in SPLIT_STRATEGIES:
        raise HTTPException(
            status_code=400, detail=f"Invalid strategy. Allowed: {', '.join(SPLIT_STRATEGIES)}"
        )
    service = RestaurantService(db)
    try:
        result = await service.split_ticket(
            ticket_id, data.strategy, user_id=client.user_id, n_ways=data.n_ways
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if result is None:
        raise HTTPException(status_code=404, detail="Order ticket not found")
    return result


# ---------- Service charge + check (F-061) ----------
@router.put("/order-tickets/{ticket_id}/service-charge", response_model=OrderTicketResponse)
async def set_service_charge(
    ticket_id: int,
    data: ServiceChargeRequest,
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """Apply an optional service-charge % to a ticket, outside the VAT base (F-061)."""
    service = RestaurantService(db)
    try:
        ticket = await service.set_service_charge(
            ticket_id, data.service_charge_pct, user_id=client.user_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if ticket is None:
        raise HTTPException(status_code=404, detail="Order ticket not found")
    return ticket


@router.get("/order-tickets/{ticket_id}/check")
async def get_ticket_check(
    ticket_id: int,
    tip_amount: float = Query(0, ge=0),
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """Compute a ticket's bill — VAT on goods only, service charge + tip outside it (F-061).

    Returns the normalized cart the settle path consumes: goods subtotal, VAT,
    invoice total, the service charge as its own non-taxable line, the tip, and the
    ``amount_due`` the tenders must cover (total + service charge + tip).
    """
    service = RestaurantService(db)
    # MA-05: the master's global VAT rate is authoritative (same as the POS path).
    vat_rate = await get_effective_tax_rate(db, 15.0)
    try:
        result = await service.compute_check(
            ticket_id, user_id=client.user_id, vat_rate=vat_rate, tip_amount=tip_amount
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if result is None:
        raise HTTPException(status_code=404, detail="Order ticket not found")
    return result


@router.post("/order-tickets/{ticket_id}/check")
async def print_ticket_check(
    ticket_id: int,
    data: CheckRequest,
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """Print an 80mm always-Arabic **proforma** check — *فاتورة مبدئية* (F-059).

    The non-fiscal bill the customer reviews before paying: full breakdown (goods,
    VAT, service charge, tip, amount due) but **no QR and no stamp**, so it can
    never be mistaken for a tax invoice. Renders in Arabic regardless of UI
    language.
    """
    service = RestaurantService(db)
    vat_rate = await get_effective_tax_rate(db, 15.0)
    tip = round(float(data.tip_amount or 0), 2)
    if tip < 0:
        raise HTTPException(status_code=400, detail="tip_amount cannot be negative")
    proforma = await service.build_proforma(
        ticket_id, user_id=client.user_id, client=client, vat_rate=vat_rate, tip_amount=tip
    )
    if proforma is None:
        raise HTTPException(status_code=404, detail="Order ticket not found")
    return proforma


def _settle_tender_specs(data: "SettleRequest", amount_due: float) -> List[dict]:
    """Derive the per-tender capture specs from a settle request (split or single)."""
    if data.payments:
        return [
            {
                "tender_type": p.tender_type or p.method,
                "amount": p.amount,
                "token": p.token,
                "simulate": p.simulate,
                "terminal_id": p.terminal_id,
                "gift_card_code": p.gift_card_code,
            }
            for p in data.payments
        ]
    return [
        {
            "tender_type": data.payment_method,
            "amount": amount_due,
            "token": data.payment_token,
            "simulate": data.payment_simulate,
            "terminal_id": data.payment_terminal_id,
            "gift_card_code": data.payment_gift_card_code,
        }
    ]


@router.post("/order-tickets/{ticket_id}/settle", response_model=SettleResponse)
async def settle_ticket_endpoint(
    ticket_id: int,
    data: SettleRequest,
    background_tasks: BackgroundTasks,
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """Settle a ticket into a real ZATCA invoice via the shared sale core (F-059).

    Builds the normalized cart from the ticket (lines + modifiers + combos +
    service charge + BOM components) and mints a fiscal sale through the **same**
    atomic path the POS uses. On success the ticket is ``settled`` and the table
    freed; a declined card rolls the whole thing back (402) — ticket stays open,
    table stays occupied, no invoice is minted.
    """
    service = RestaurantService(db)
    vat_rate = await get_effective_tax_rate(db, 15.0)
    tip = round(float(data.tip_amount or 0), 2)
    if tip < 0:
        raise HTTPException(status_code=400, detail="tip_amount cannot be negative")

    # Compute the authoritative amount due so the tenders can be validated against
    # it before any fiscal side effect runs.
    check = await service.compute_check(
        ticket_id, user_id=client.user_id, vat_rate=vat_rate, tip_amount=tip
    )
    if check is None:
        raise HTTPException(status_code=404, detail="Order ticket not found")
    amount_due = check["amount_due"]

    payment_breakdown_json: Optional[str] = None
    payment_method = data.payment_method
    if data.payments:
        paid_total = round(sum(p.amount for p in data.payments), 2)
        if abs(paid_total - amount_due) > 0.01:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Payment breakdown total {paid_total:.2f} does not match "
                    f"amount due {amount_due:.2f}"
                ),
            )

        def _redacted(p: "SettlePayment") -> dict:
            d = p.model_dump()
            if d.get("gift_card_code"):
                d["gift_card_code"] = "****" + str(d["gift_card_code"])[-4:]
            return d

        payment_breakdown_json = json.dumps(
            [_redacted(p) for p in data.payments], ensure_ascii=False
        )
        methods = [p.method for p in data.payments]
        payment_method = "mixed" if len(set(methods)) > 1 else methods[0]

    tender_specs = _settle_tender_specs(data, amount_due)
    buyer_vat = (data.customer_vat_number or "").strip() or None

    try:
        settled = await service.settle_ticket(
            ticket_id,
            client.user_id,
            client,
            vat_rate,
            tender_specs=tender_specs,
            tip_amount=tip,
            payment_method=payment_method,
            payment_breakdown_json=payment_breakdown_json,
            customer_name=data.customer_name,
            customer_vat_number=buyer_vat,
            allow_negative_stock=data.allow_negative_stock,
        )
    except ValueError as e:
        # Already settled/void, or an empty ticket.
        raise HTTPException(status_code=409, detail=str(e))
    if settled is None:
        raise HTTPException(status_code=404, detail="Order ticket not found")

    result = settled["result"]
    chk = settled["check"]
    ticket = settled["ticket"]
    txn = result.transaction

    # Report the document out-of-band (never blocks the committed sale); skipped
    # when the client has ZATCA disabled (no document to report).
    if result.document_id is not None:
        background_tasks.add_task(
            zatca_sale.report_document_background, result.document_id, client.id
        )

    # Always-Arabic 80mm receipt for the settled invoice (service charge + tip both
    # shown outside the VAT base, fiscal QR embedded).
    receipt_base64 = build_receipt_base64(
        seller_name=client.business_name or "Business",
        vat_number=client.vat_number or "",
        invoice_number=txn.invoice_number,
        issue_date=(txn.created_at.strftime("%Y-%m-%d %H:%M") if txn.created_at else ""),
        line_items=[
            {
                "name": ln["name"],
                "name_ar": None,
                "quantity": ln["qty"],
                "price": ln["unit_price"],
                "discount": 0,
            }
            for ln in chk["lines"]
        ],
        subtotal=chk["subtotal"],
        discount=0,
        vat_amount=chk["vat_amount"],
        total_amount=chk["total_amount"],
        tip_amount=chk["tip_amount"],
        service_charge=chk["service_charge"]["amount"],
        zatca_qr=result.stamped_qr or "",
    )

    return SettleResponse(
        ticket_id=ticket_id,
        transaction_id=txn.id,
        invoice_number=txn.invoice_number,
        subtotal=chk["subtotal"],
        vat_amount=chk["vat_amount"],
        total_amount=chk["total_amount"],
        service_charge=chk["service_charge"]["amount"],
        tip_amount=chk["tip_amount"],
        amount_due=chk["amount_due"],
        zatca_document_id=result.document_id,
        zatca_status="signed" if result.document_id is not None else "disabled",
        zatca_qr=result.stamped_qr,
        zatca_qr_base64=(
            zatca_service_mod.render_qr_png_base64(result.stamped_qr)
            if result.stamped_qr
            else None
        ),
        receipt_base64=receipt_base64,
        ticket_status=ticket.status or "settled",
        table_freed=ticket.table_id is not None,
    )


@router.get("/all-day-count")
async def all_day_fired_count(
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """All-day count of fired items across the caller's open tickets (RST-02)."""
    service = RestaurantService(db)
    return await service.all_day_fired_count(user_id=client.user_id)


# ---------- Modifier group routes (F-056) ----------
@router.get("/modifier-groups", response_model=List[ModifierGroupResponse])
async def list_modifier_groups(
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """List the caller's modifier groups (F-056)."""
    service = RestaurantService(db)
    return await service.list_modifier_groups(user_id=client.user_id)


@router.post("/modifier-groups", response_model=ModifierGroupResponse, status_code=201)
async def create_modifier_group(
    data: ModifierGroupData,
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """Create a modifier group with required + min/max rules (F-056)."""
    service = RestaurantService(db)
    try:
        return await service.create_modifier_group(
            data.model_dump(), user_id=client.user_id, client_id=client.id
        )
    except Exception as e:
        logger.error(f"Error creating modifier group: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.put("/modifier-groups/{group_id}", response_model=ModifierGroupResponse)
async def update_modifier_group(
    group_id: int,
    data: ModifierGroupUpdateData,
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """Update a modifier group (requires ownership)."""
    service = RestaurantService(db)
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    result = await service.update_modifier_group(group_id, updates, user_id=client.user_id)
    if not result:
        raise HTTPException(status_code=404, detail="Modifier group not found")
    return result


@router.delete("/modifier-groups/{group_id}")
async def delete_modifier_group(
    group_id: int,
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """Delete a modifier group and its modifiers/attachments (requires ownership)."""
    service = RestaurantService(db)
    ok = await service.delete_modifier_group(group_id, user_id=client.user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Modifier group not found")
    return {"message": "Modifier group deleted successfully", "id": group_id}


# ---------- Modifier routes (F-056) ----------
@router.get("/modifier-groups/{group_id}/modifiers", response_model=List[ModifierResponse])
async def list_modifiers(
    group_id: int,
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """List a group's modifiers (owner-scoped, F-056)."""
    service = RestaurantService(db)
    group = await service.get_modifier_group(group_id, user_id=client.user_id)
    if not group:
        raise HTTPException(status_code=404, detail="Modifier group not found")
    return await service.list_modifiers(group_id, user_id=client.user_id)


@router.post("/modifier-groups/{group_id}/modifiers", response_model=ModifierResponse, status_code=201)
async def create_modifier(
    group_id: int,
    data: ModifierData,
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """Add a modifier (bilingual name + price delta) to a group (F-056)."""
    service = RestaurantService(db)
    modifier = await service.create_modifier(
        group_id, data.model_dump(), user_id=client.user_id, client_id=client.id
    )
    if modifier is None:
        raise HTTPException(status_code=404, detail="Modifier group not found")
    return modifier


@router.put("/modifiers/{modifier_id}", response_model=ModifierResponse)
async def update_modifier(
    modifier_id: int,
    data: ModifierUpdateData,
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """Update a modifier (requires ownership)."""
    service = RestaurantService(db)
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    result = await service.update_modifier(modifier_id, updates, user_id=client.user_id)
    if not result:
        raise HTTPException(status_code=404, detail="Modifier not found")
    return result


@router.delete("/modifiers/{modifier_id}")
async def delete_modifier(
    modifier_id: int,
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """Delete a modifier (requires ownership)."""
    service = RestaurantService(db)
    ok = await service.delete_modifier(modifier_id, user_id=client.user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Modifier not found")
    return {"message": "Modifier deleted successfully", "id": modifier_id}


# ---------- Product ↔ modifier-group attachment routes (F-056) ----------
@router.get("/products/{product_id}/modifier-groups")
async def list_product_modifier_groups(
    product_id: int,
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """List the modifier groups (with their modifiers) attached to a product (F-056)."""
    service = RestaurantService(db)
    groups = await service.list_product_groups(product_id, user_id=client.user_id)
    return {"items": groups, "total": len(groups)}


@router.post("/products/{product_id}/modifier-groups/{group_id}", status_code=201)
async def attach_modifier_group(
    product_id: int,
    group_id: int,
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """Attach a modifier group to a product (idempotent, F-056)."""
    service = RestaurantService(db)
    link = await service.attach_group_to_product(
        product_id, group_id, user_id=client.user_id, client_id=client.id
    )
    if link is None:
        raise HTTPException(status_code=404, detail="Product or modifier group not found")
    return {"message": "Modifier group attached", "product_id": product_id, "group_id": group_id}


@router.delete("/products/{product_id}/modifier-groups/{group_id}")
async def detach_modifier_group(
    product_id: int,
    group_id: int,
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """Detach a modifier group from a product (F-056)."""
    service = RestaurantService(db)
    ok = await service.detach_group_from_product(product_id, group_id, user_id=client.user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Attachment not found")
    return {"message": "Modifier group detached", "product_id": product_id, "group_id": group_id}


# ---------- Combo routes (F-056) ----------
async def _combo_to_response(service: RestaurantService, combo, user_id: str) -> dict:
    """Serialize a combo with parsed components + the (overridden) component sum."""
    component_sum = await service.combo_component_sum(combo, user_id)
    return {
        "id": combo.id,
        "user_id": combo.user_id,
        "client_id": combo.client_id,
        "name": combo.name,
        "name_ar": combo.name_ar,
        "bundle_price": float(combo.bundle_price or 0),
        "components": service._load_components(combo),
        "component_sum": component_sum,
        "is_active": combo.is_active,
    }


@router.get("/combos", response_model=List[ComboResponse])
async def list_combos(
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """List the caller's combos with each one's component sum (F-056)."""
    service = RestaurantService(db)
    combos = await service.list_combos(user_id=client.user_id)
    return [await _combo_to_response(service, c, client.user_id) for c in combos]


@router.get("/combos/{combo_id}", response_model=ComboResponse)
async def get_combo(
    combo_id: int,
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """Get a combo, including its component sum vs bundle price (F-056)."""
    service = RestaurantService(db)
    combo = await service.get_combo(combo_id, user_id=client.user_id)
    if not combo:
        raise HTTPException(status_code=404, detail="Combo not found")
    return await _combo_to_response(service, combo, client.user_id)


@router.post("/combos", response_model=ComboResponse, status_code=201)
async def create_combo(
    data: ComboData,
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """Create a combo — components + a bundle price that overrides their sum (F-056)."""
    service = RestaurantService(db)
    try:
        combo = await service.create_combo(
            data.model_dump(), user_id=client.user_id, client_id=client.id
        )
    except Exception as e:
        logger.error(f"Error creating combo: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    return await _combo_to_response(service, combo, client.user_id)


@router.put("/combos/{combo_id}", response_model=ComboResponse)
async def update_combo(
    combo_id: int,
    data: ComboUpdateData,
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """Update a combo (requires ownership)."""
    service = RestaurantService(db)
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    combo = await service.update_combo(combo_id, updates, user_id=client.user_id)
    if not combo:
        raise HTTPException(status_code=404, detail="Combo not found")
    return await _combo_to_response(service, combo, client.user_id)


@router.delete("/combos/{combo_id}")
async def delete_combo(
    combo_id: int,
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """Delete a combo (requires ownership)."""
    service = RestaurantService(db)
    ok = await service.delete_combo(combo_id, user_id=client.user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Combo not found")
    return {"message": "Combo deleted successfully", "id": combo_id}


# ---------- Bill-of-materials routes (F-062) ----------
@router.get("/products/{product_id}/bom", response_model=BomListResponse)
async def list_product_bom(
    product_id: int,
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """List a product's BOM components + its rolled-up cost-of-goods (F-062)."""
    service = RestaurantService(db)
    items = await service.list_bom(product_id, user_id=client.user_id)
    cogs = await service.parent_cogs(product_id, user_id=client.user_id)
    return {"items": items, "total": len(items), "cost_of_goods": cogs}


@router.post("/products/{product_id}/bom", response_model=BomEntryResponse, status_code=201)
async def add_product_bom(
    product_id: int,
    data: BomEntryData,
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """Add a component (with a qty-per) to a product's BOM (F-062)."""
    service = RestaurantService(db)
    try:
        entry = await service.create_bom_entry(
            product_id, data.model_dump(), user_id=client.user_id, client_id=client.id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if entry is None:
        raise HTTPException(status_code=404, detail="Parent or component product not found")
    return entry


@router.put("/bom/{bom_id}", response_model=BomEntryResponse)
async def update_bom_entry(
    bom_id: int,
    data: BomEntryUpdateData,
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """Update a BOM entry's qty-per (requires ownership, F-062)."""
    service = RestaurantService(db)
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    try:
        entry = await service.update_bom_entry(bom_id, updates, user_id=client.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if entry is None:
        raise HTTPException(status_code=404, detail="BOM entry not found")
    return entry


@router.delete("/bom/{bom_id}")
async def delete_bom_entry(
    bom_id: int,
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """Delete a BOM entry (requires ownership, F-062)."""
    service = RestaurantService(db)
    ok = await service.delete_bom_entry(bom_id, user_id=client.user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="BOM entry not found")
    return {"message": "BOM entry deleted successfully", "id": bom_id}


# ---------- Prep-station routes (F-057) ----------
@router.get("/kds/stations", response_model=List[PrepStationResponse])
async def list_prep_stations(
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """List the caller's kitchen prep-stations (F-057)."""
    service = RestaurantService(db)
    return await service.list_prep_stations(user_id=client.user_id)


@router.post("/kds/stations", response_model=PrepStationResponse, status_code=201)
async def create_prep_station(
    data: PrepStationData,
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """Define a prep-station with a bilingual name (F-057)."""
    service = RestaurantService(db)
    try:
        return await service.create_prep_station(
            data.model_dump(), user_id=client.user_id, client_id=client.id
        )
    except Exception as e:
        logger.error(f"Error creating prep station: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.put("/kds/stations/{station_id}", response_model=PrepStationResponse)
async def update_prep_station(
    station_id: int,
    data: PrepStationUpdateData,
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """Update a prep-station (requires ownership, F-057)."""
    service = RestaurantService(db)
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    result = await service.update_prep_station(station_id, updates, user_id=client.user_id)
    if not result:
        raise HTTPException(status_code=404, detail="Prep station not found")
    return result


@router.delete("/kds/stations/{station_id}")
async def delete_prep_station(
    station_id: int,
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """Delete a prep-station (requires ownership, F-057)."""
    service = RestaurantService(db)
    ok = await service.delete_prep_station(station_id, user_id=client.user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Prep station not found")
    return {"message": "Prep station deleted successfully", "id": station_id}


# ---------- Kitchen Display (KDS) routes (F-057) ----------
@router.get("/kds/tickets")
async def list_kds_tickets(
    status: Optional[str] = Query("active"),
    station_id: Optional[int] = Query(None),
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """The kitchen board snapshot — fired cards the caller owns (F-057).

    Defaults to ``active`` cards (those still cooking); pass ``status=bumped`` to
    review completed cards or ``status=`` (empty) for all. The real-time updates
    ride the SSE stream below; this is the initial/poll snapshot.
    """
    if status == "":
        status = None
    if status is not None and status not in KDS_STATUSES:
        raise HTTPException(
            status_code=400, detail=f"Invalid status. Allowed: {', '.join(KDS_STATUSES)}"
        )
    service = RestaurantService(db)
    cards = await service.list_kds_tickets(
        user_id=client.user_id, status=status, station_id=station_id
    )
    items = [service._kds_to_dict(c) for c in cards]
    return {"items": items, "total": len(items)}


@router.post("/kds/{kds_id}/bump")
async def bump_kds_ticket(
    kds_id: int,
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """Mark a card done — clear it from the active board (F-057).

    Advances the card ``active -> bumped`` and its source order lines to
    ``bumped`` so the server's screen and the kitchen agree.
    """
    service = RestaurantService(db)
    card = await service.bump_kds_ticket(kds_id, user_id=client.user_id)
    if card is None:
        raise HTTPException(status_code=404, detail="KDS ticket not found")
    return card


@router.post("/kds/{kds_id}/recall")
async def recall_kds_ticket(
    kds_id: int,
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """Restore a mistakenly-bumped card to the active board (F-057)."""
    service = RestaurantService(db)
    card = await service.recall_kds_ticket(kds_id, user_id=client.user_id)
    if card is None:
        raise HTTPException(status_code=404, detail="KDS ticket not found")
    return card


@router.get("/kds/{kds_id}/kot")
async def print_kds_kot(
    kds_id: int,
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """Render the per-station 80mm **always-Arabic** KOT for a card (F-057).

    Modifiers are grouped under each course and **no prices appear** — a kitchen
    ticket carries no money, no QR, no stamp. Returns the structured KOT model
    plus the base64 ESC/POS stream the browser streams to the station printer.
    """
    service = RestaurantService(db)
    payload = await service.kot_payload(kds_id, user_id=client.user_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="KDS ticket not found")
    station_label = payload.get("station_name_ar") or payload.get("station_name") or ""
    kot_base64 = build_kot_base64(
        station_name=station_label,
        order_ref=str(payload.get("order_ticket_id") or ""),
        table_label=str(payload.get("table_id") or ""),
        fired_at=(payload.get("fired_at") or "")[:16].replace("T", " "),
        courses=payload.get("courses") or [],
    )
    return {**payload, "kot_base64": kot_base64}


@router.get("/kds/stream")
async def kds_stream(
    token: str = Query(..., description="Bearer JWT (EventSource cannot set headers)"),
    db: AsyncSession = Depends(get_db),
):
    """Real-time Kitchen-Display feed over **Server-Sent Events** (F-057).

    The browser ``EventSource`` can't set an Authorization header, so the JWT is
    passed as a query param and run through the same double-gate as every other
    restaurant route. The stream emits an initial ``snapshot`` of the active board,
    then ``fired`` / ``bumped`` / ``recalled`` events as they happen (≤1s, fanned
    out by the in-process broker) with periodic ``: keepalive`` comments so proxies
    don't drop an idle connection.
    """
    try:
        payload = decode_access_token(token)
    except AccessTokenError:
        raise HTTPException(status_code=401, detail="Invalid authentication token")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid authentication token")
    client = await _resolve_restaurant_client(db, user_id)
    owner_id = client.user_id

    queue = kds_broker.subscribe(owner_id)

    async def event_gen():
        try:
            # Initial snapshot of the active board (fresh session so we never hold
            # the request session open for the life of the stream).
            async with db_manager.async_session_maker() as snap_db:
                service = RestaurantService(snap_db)
                cards = await service.list_kds_tickets(user_id=owner_id, status="active")
                snapshot = [service._kds_to_dict(c) for c in cards]
            yield f"event: snapshot\ndata: {json.dumps({'items': snapshot})}\n\n"

            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    # Keepalive comment — keeps proxies/load-balancers from idling out.
                    yield ": keepalive\n\n"
        finally:
            kds_broker.unsubscribe(owner_id, queue)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
