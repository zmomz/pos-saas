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
import logging
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.auth import get_current_user
from dependencies.features import is_feature_enabled
from models.clients import Clients
from schemas.auth import UserResponse
from services.restaurant import (
    ORDER_TYPES,
    SPLIT_STRATEGIES,
    TABLE_STATES,
    RestaurantService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/restaurant", tags=["restaurant"])

# business_type values that unlock the restaurant vertical.
RESTAURANT_BUSINESS_TYPES = ("restaurant", "both")


# ---------- Gate dependency ----------
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
    result = await db.execute(select(Clients).where(Clients.user_id == str(current_user.id)))
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
