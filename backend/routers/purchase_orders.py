import json
import logging
from typing import List, Optional

from datetime import datetime, date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.purchase_orders import Purchase_ordersService
from dependencies.auth import get_admin_user, get_current_user
from dependencies.tenancy import TenantScope, get_owner_id, get_tenant_scope
from schemas.auth import UserResponse

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/purchase_orders", tags=["purchase_orders"])


# ---------- Pydantic Schemas ----------
class Purchase_ordersData(BaseModel):
    """Entity data schema (for create/update)"""
    client_id: int = None
    supplier_id: int = None
    order_number: str
    status: str
    total_amount: float = None
    items_json: str = None
    notes: str = None
    expected_date: str = None
    received_date: str = None


class Purchase_ordersUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    client_id: Optional[int] = None
    supplier_id: Optional[int] = None
    order_number: Optional[str] = None
    status: Optional[str] = None
    total_amount: Optional[float] = None
    items_json: Optional[str] = None
    notes: Optional[str] = None
    expected_date: Optional[str] = None
    received_date: Optional[str] = None


class Purchase_ordersResponse(BaseModel):
    """Entity response schema"""
    id: int
    user_id: str
    client_id: Optional[int] = None
    supplier_id: Optional[int] = None
    order_number: str
    status: str
    total_amount: Optional[float] = None
    items_json: Optional[str] = None
    notes: Optional[str] = None
    expected_date: Optional[str] = None
    received_date: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class Purchase_ordersListResponse(BaseModel):
    """List response schema"""
    items: List[Purchase_ordersResponse]
    total: int
    skip: int
    limit: int


class Purchase_ordersBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[Purchase_ordersData]


class Purchase_ordersBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: Purchase_ordersUpdateData


class Purchase_ordersBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[Purchase_ordersBatchUpdateItem]


class Purchase_ordersBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=Purchase_ordersListResponse)
async def query_purchase_orderss(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Query purchase_orderss with filtering, sorting, and pagination (user can only see their own records)"""
    logger.debug(f"Querying purchase_orderss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = Purchase_ordersService(db)
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
        logger.debug(f"Found {result['total']} purchase_orderss")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying purchase_orderss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=Purchase_ordersListResponse)
async def query_purchase_orderss_all(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    # Query purchase_orderss with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying purchase_orderss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = Purchase_ordersService(db)
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
        logger.debug(f"Found {result['total']} purchase_orderss")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying purchase_orderss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{id}", response_model=Purchase_ordersResponse)
async def get_purchase_orders(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Get a single purchase_orders by ID (user can only see their own records)"""
    logger.debug(f"Fetching purchase_orders with id: {id}, fields={fields}")
    
    service = Purchase_ordersService(db)
    try:
        result = await service.get_by_id(id, user_id=scope.owner_user_id)
        if not result:
            logger.warning(f"Purchase_orders with id {id} not found")
            raise HTTPException(status_code=404, detail="Purchase_orders not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching purchase_orders {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=Purchase_ordersResponse, status_code=201)
async def create_purchase_orders(
    data: Purchase_ordersData,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Create a new purchase_orders"""
    logger.debug(f"Creating new purchase_orders with data: {data}")
    
    service = Purchase_ordersService(db)
    try:
        result = await service.create(data.model_dump(), user_id=(scope.owner_user_id or str(current_user.id)))
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create purchase_orders")
        
        logger.info(f"Purchase_orders created successfully with id: {result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error creating purchase_orders: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating purchase_orders: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


class ReceiveLineInput(BaseModel):
    """A single line being received now (a partial receipt against the PO)."""
    product_id: int
    quantity: int
    cost: Optional[float] = None


class ReceivePurchaseOrderRequest(BaseModel):
    """Optional body for ``/receive`` (INV-07/INV-09).

    - ``branch_id`` — receive into the per-branch stock ledger the POS deducts
      from (omit to fall back to the client-level aggregate ``products.quantity``).
    - ``lines`` — a partial receipt: only these ``{product_id, quantity, cost?}``
      are received (omit to receive the full remaining balance of every line).
    """
    branch_id: Optional[int] = None
    lines: Optional[List[ReceiveLineInput]] = None


class ReceivePurchaseOrderResponse(BaseModel):
    id: int
    status: str
    received_date: Optional[str] = None
    received_items: int
    message: str


def _remaining_by_product(items: list) -> dict:
    """Outstanding (ordered − already-received) quantity per product across the PO."""
    remaining: dict = {}
    for line in items:
        pid = line.get("product_id")
        if pid is None:
            continue
        ordered = int(line.get("quantity") or 0)
        already = int(line.get("received") or 0)
        remaining[pid] = remaining.get(pid, 0) + max(0, ordered - already)
    return remaining


def _apply_received_to_lines(items: list, to_receive: dict) -> dict:
    """Fold ``to_receive`` (product_id → qty) into each line's ``received`` field.

    Fills lines for a product in order up to each line's ordered quantity so the
    PO's own ``items_json`` is the durable record of how much has been received
    (enabling successive partial receipts to complete to ``received`` exactly once).
    Returns the actual quantity applied per product.
    """
    remaining = dict(to_receive)
    applied: dict = {}
    for line in items:
        pid = line.get("product_id")
        if pid is None:
            continue
        ordered = int(line.get("quantity") or 0)
        already = int(line.get("received") or 0)
        line_remaining = max(0, ordered - already)
        want = remaining.get(pid, 0)
        if want <= 0 or line_remaining <= 0:
            continue
        take = min(want, line_remaining)
        line["received"] = already + take
        remaining[pid] = want - take
        applied[pid] = applied.get(pid, 0) + take
    return applied


@router.post("/{id}/receive", response_model=ReceivePurchaseOrderResponse)
async def receive_purchase_order(
    id: int,
    request: Optional[ReceivePurchaseOrderRequest] = Body(None),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Receive a purchase order into stock and advance its status (INV-07/INV-09).

    Parses ``items_json`` (a list of ``{product_id, quantity, cost?}``) and adds
    the received quantities to stock. Improvements over the original flat receive:

    - **Branch-aware (INV-07):** when ``branch_id`` is given the stock lands in the
      per-branch ledger (``product_branch_stock``) the POS actually deducts from,
      not just the client-level aggregate.
    - **Partial receipts (INV-07):** an optional ``lines`` body receives only the
      selected quantities; the PO becomes ``partially_received`` while a balance
      remains and ``received`` only once every line is fully received.
    - **Moving-average cost (INV-09):** ``cost_price`` is re-weighted by the prior
      on-hand at the receiving location, not flat-overwritten — so margin reports
      reflect real landed cost.

    Idempotent guard: a fully-received PO is rejected so stock is never double-counted.
    """
    from sqlalchemy import select

    from models.products import Products
    from models.purchase_orders import Purchase_orders

    po = (
        await db.execute(
            select(Purchase_orders).where(
                Purchase_orders.id == id,
                Purchase_orders.user_id == owner_id,
            )
        )
    ).scalar_one_or_none()
    if not po:
        raise HTTPException(status_code=404, detail="Purchase_orders not found")
    if (po.status or "").lower() == "received":
        raise HTTPException(status_code=400, detail="Purchase order already received")

    try:
        items = json.loads(po.items_json) if po.items_json else []
    except (ValueError, TypeError):
        items = []
    if not isinstance(items, list):
        items = []

    remaining_by_pid = _remaining_by_product(items)

    # A legacy PO with no receivable product lines (e.g. a product_name-only PO
    # from the older create form) is simply closed — there is nothing to land in
    # stock, but the operator still wants it marked received.
    if not remaining_by_pid:
        received_date = date.today().isoformat()
        po.status = "received"
        po.received_date = received_date
        await db.commit()
        return ReceivePurchaseOrderResponse(
            id=id,
            status="received",
            received_date=received_date,
            received_items=0,
            message="Purchase order closed (no stock lines to receive)",
        )

    branch_id = request.branch_id if request else None
    cost_override: dict = {}
    if request and request.lines:
        to_receive: dict = {}
        for line_in in request.lines:
            if line_in.quantity is None or line_in.quantity <= 0:
                continue
            to_receive[line_in.product_id] = (
                to_receive.get(line_in.product_id, 0) + int(line_in.quantity)
            )
            if line_in.cost is not None:
                cost_override[line_in.product_id] = line_in.cost
        # Reject receiving more than the outstanding balance for any product.
        for pid, qty in to_receive.items():
            if qty > remaining_by_pid.get(pid, 0):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Cannot receive {qty} unit(s) of product {pid}: only "
                        f"{remaining_by_pid.get(pid, 0)} remaining on this order"
                    ),
                )
    else:
        # No explicit lines → receive the full remaining balance of every line.
        to_receive = {pid: qty for pid, qty in remaining_by_pid.items() if qty > 0}

    if not to_receive:
        raise HTTPException(status_code=400, detail="Nothing left to receive on this order")

    # Default per-product cost = the PO line's cost (overridable per receive line).
    cost_by_pid: dict = {}
    for line in items:
        pid = line.get("product_id")
        if pid is not None and line.get("cost") is not None:
            cost_by_pid[pid] = line.get("cost")

    applied = _apply_received_to_lines(items, to_receive)

    client = None
    if branch_id is not None:
        from routers.pos import get_client_for_user

        client = await get_client_for_user(db, owner_id)

    received_lines = 0
    for pid, qty in applied.items():
        if qty <= 0:
            continue
        product = (
            await db.execute(
                select(Products).where(
                    Products.id == pid, Products.user_id == owner_id
                )
            )
        ).scalar_one_or_none()
        if not product:
            continue
        received_lines += 1
        cost = cost_override.get(pid, cost_by_pid.get(pid))

        if branch_id is not None:
            from services.branch_stock import get_or_init_row

            row = await get_or_init_row(
                db, owner_id, client.id, branch_id, product
            )
            prior_qty = row.quantity or 0
            row.quantity = prior_qty + qty
        else:
            prior_qty = product.quantity or 0
            product.quantity = prior_qty + qty

        # Moving-average cost (INV-09): re-weight by the on-hand at the location
        # being replenished, never a flat overwrite.
        if cost is not None:
            prior_cost = product.cost_price or 0
            denom = prior_qty + qty
            product.cost_price = (
                ((prior_qty * prior_cost) + (qty * cost)) / denom if denom > 0 else cost
            )

    # Fully received only when every line's received reaches its ordered quantity.
    fully_received = all(
        int(line.get("received") or 0) >= int(line.get("quantity") or 0)
        for line in items
        if line.get("product_id") is not None
    )
    new_status = "received" if fully_received else "partially_received"
    received_date = date.today().isoformat() if fully_received else po.received_date

    po.items_json = json.dumps(items)
    po.status = new_status
    po.received_date = received_date
    await db.commit()

    return ReceivePurchaseOrderResponse(
        id=id,
        status=new_status,
        received_date=received_date,
        received_items=received_lines,
        message=(
            f"Received {received_lines} line(s) into "
            f"{'branch' if branch_id is not None else 'client'} stock"
            + ("" if fully_received else "; order partially received")
        ),
    )


class BranchAllocationInput(BaseModel):
    """One branch's slice of a central PO distribution (#220 central purchasing)."""
    branch_id: int
    lines: List[ReceiveLineInput]


class DistributePurchaseOrderRequest(BaseModel):
    """Distribute a central PO's received goods across several branches at once.

    Each allocation lands its ``lines`` into that branch's per-branch stock ledger
    (``product_branch_stock``). The outstanding-balance guard and the
    partial→received status walk are applied against the *sum* of every allocation,
    so a chain buys once centrally and splits the delivery across its branches.
    """
    allocations: List[BranchAllocationInput]


class DistributePurchaseOrderResponse(BaseModel):
    id: int
    status: str
    received_date: Optional[str] = None
    branches: int
    received_items: int
    message: str


@router.post("/{id}/distribute", response_model=DistributePurchaseOrderResponse)
async def distribute_purchase_order(
    id: int,
    request: DistributePurchaseOrderRequest = Body(...),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Central purchasing (#220): receive a central PO and distribute its goods
    across multiple branches in one operation.

    Mirrors ``/receive`` but fans the delivery out: each allocation's lines land in
    that branch's ledger (``product_branch_stock``), the combined receipt is folded
    into the PO's ``items_json`` (so the order walks ``partially_received`` →
    ``received`` exactly once across successive distributions), over-allocating past
    the outstanding balance for any product is rejected wholesale, and ``cost_price``
    is re-weighted by a moving average over the destinations being replenished.
    """
    from sqlalchemy import select

    from models.products import Products
    from models.purchase_orders import Purchase_orders

    po = (
        await db.execute(
            select(Purchase_orders).where(
                Purchase_orders.id == id,
                Purchase_orders.user_id == owner_id,
            )
        )
    ).scalar_one_or_none()
    if not po:
        raise HTTPException(status_code=404, detail="Purchase_orders not found")
    if (po.status or "").lower() == "received":
        raise HTTPException(status_code=400, detail="Purchase order already received")

    try:
        items = json.loads(po.items_json) if po.items_json else []
    except (ValueError, TypeError):
        items = []
    if not isinstance(items, list):
        items = []

    remaining_by_pid = _remaining_by_product(items)
    if not remaining_by_pid:
        raise HTTPException(status_code=400, detail="This purchase order has no stock lines to distribute")

    # Total requested per product across *all* branches must fit the outstanding
    # balance — central purchasing cannot over-receive any line.
    total_by_pid: dict = {}
    for alloc in request.allocations:
        for line in alloc.lines:
            if line.quantity is None or line.quantity <= 0:
                continue
            total_by_pid[line.product_id] = total_by_pid.get(line.product_id, 0) + int(line.quantity)
    if not total_by_pid:
        raise HTTPException(status_code=400, detail="No quantities to distribute")
    for pid, qty in total_by_pid.items():
        if qty > remaining_by_pid.get(pid, 0):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Cannot distribute {qty} unit(s) of product {pid}: only "
                    f"{remaining_by_pid.get(pid, 0)} remaining on this order"
                ),
            )

    # Default per-product cost = the PO line's cost (overridable per allocation line).
    cost_by_pid: dict = {}
    for line in items:
        pid = line.get("product_id")
        if pid is not None and line.get("cost") is not None:
            cost_by_pid[pid] = line.get("cost")

    # Fold the combined receipt into the PO lines once (drives the status walk).
    applied = _apply_received_to_lines(items, total_by_pid)

    from routers.pos import get_client_for_user
    from services.branch_stock import get_or_init_row

    client = await get_client_for_user(db, owner_id)

    # Accumulate the moving-average inputs per product across every destination.
    ma_prior_qty: dict = {}
    ma_prior_cost: dict = {}
    ma_in_qty: dict = {}
    ma_in_value: dict = {}
    branches_touched = set()
    for alloc in request.allocations:
        for line in alloc.lines:
            if line.quantity is None or line.quantity <= 0:
                continue
            product = (
                await db.execute(
                    select(Products).where(
                        Products.id == line.product_id, Products.user_id == owner_id
                    )
                )
            ).scalar_one_or_none()
            if not product:
                continue
            row = await get_or_init_row(db, owner_id, client.id, alloc.branch_id, product)
            prior_qty = row.quantity or 0
            row.quantity = prior_qty + int(line.quantity)
            branches_touched.add(alloc.branch_id)

            cost = line.cost if line.cost is not None else cost_by_pid.get(line.product_id)
            if cost is not None:
                ma_prior_qty[line.product_id] = ma_prior_qty.get(line.product_id, 0) + prior_qty
                ma_prior_cost.setdefault(line.product_id, product.cost_price or 0)
                ma_in_qty[line.product_id] = ma_in_qty.get(line.product_id, 0) + int(line.quantity)
                ma_in_value[line.product_id] = ma_in_value.get(line.product_id, 0) + int(line.quantity) * cost

    # Moving-average cost (INV-09): re-weight by the on-hand at the destinations
    # being replenished, never a flat overwrite.
    for pid, in_qty in ma_in_qty.items():
        product = (
            await db.execute(
                select(Products).where(Products.id == pid, Products.user_id == owner_id)
            )
        ).scalar_one_or_none()
        if not product:
            continue
        prior_qty = ma_prior_qty.get(pid, 0)
        denom = prior_qty + in_qty
        product.cost_price = (
            ((prior_qty * ma_prior_cost.get(pid, 0)) + ma_in_value.get(pid, 0)) / denom
            if denom > 0
            else None
        )

    fully_received = all(
        int(line.get("received") or 0) >= int(line.get("quantity") or 0)
        for line in items
        if line.get("product_id") is not None
    )
    new_status = "received" if fully_received else "partially_received"
    received_date = date.today().isoformat() if fully_received else po.received_date

    po.items_json = json.dumps(items)
    po.status = new_status
    po.received_date = received_date
    await db.commit()

    received_items = sum(1 for q in applied.values() if q > 0)
    return DistributePurchaseOrderResponse(
        id=id,
        status=new_status,
        received_date=received_date,
        branches=len(branches_touched),
        received_items=received_items,
        message=(
            f"Distributed {received_items} line(s) across {len(branches_touched)} branch(es)"
            + ("" if fully_received else "; order partially received")
        ),
    )


@router.post("/batch", response_model=List[Purchase_ordersResponse], status_code=201)
async def create_purchase_orderss_batch(
    request: Purchase_ordersBatchCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Create multiple purchase_orderss in a single request"""
    logger.debug(f"Batch creating {len(request.items)} purchase_orderss")
    
    service = Purchase_ordersService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(item_data.model_dump(), user_id=(scope.owner_user_id or str(current_user.id)))
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} purchase_orderss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[Purchase_ordersResponse])
async def update_purchase_orderss_batch(
    request: Purchase_ordersBatchUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Update multiple purchase_orderss in a single request (requires ownership)"""
    logger.debug(f"Batch updating {len(request.items)} purchase_orderss")
    
    service = Purchase_ordersService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            result = await service.update(item.id, update_dict, user_id=scope.owner_user_id)
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} purchase_orderss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=Purchase_ordersResponse)
async def update_purchase_orders(
    id: int,
    data: Purchase_ordersUpdateData,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing purchase_orders (requires ownership)"""
    logger.debug(f"Updating purchase_orders {id} with data: {data}")

    service = Purchase_ordersService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        result = await service.update(id, update_dict, user_id=scope.owner_user_id)
        if not result:
            logger.warning(f"Purchase_orders with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Purchase_orders not found")
        
        logger.info(f"Purchase_orders {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating purchase_orders {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating purchase_orders {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_purchase_orderss_batch(
    request: Purchase_ordersBatchDeleteRequest,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple purchase_orderss by their IDs (requires ownership)"""
    logger.debug(f"Batch deleting {len(request.ids)} purchase_orderss")
    
    service = Purchase_ordersService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id, user_id=scope.owner_user_id)
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} purchase_orderss successfully")
        return {"message": f"Successfully deleted {deleted_count} purchase_orderss", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_purchase_orders(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Delete a single purchase_orders by ID (requires ownership)"""
    logger.debug(f"Deleting purchase_orders with id: {id}")
    
    service = Purchase_ordersService(db)
    try:
        success = await service.delete(id, user_id=scope.owner_user_id)
        if not success:
            logger.warning(f"Purchase_orders with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Purchase_orders not found")
        
        logger.info(f"Purchase_orders {id} deleted successfully")
        return {"message": "Purchase_orders deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting purchase_orders {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")