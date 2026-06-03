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
from typing import List, Optional

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
