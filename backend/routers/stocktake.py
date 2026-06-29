"""Guided stocktake endpoints — start/freeze/count/variance/approve (M4, #207).

A resumable, sessioned physical count layered on the ``stock_adjustments`` variance
primitive (INV-06). The flow the Inventory UI drives:

    start   POST /stock-counts                  → a draft session (resumable)
    freeze  POST /stock-counts/{id}/freeze       → snapshot on-hand into lines
    count   POST /stock-counts/{id}/count        → record a barcode/manual count
    variance GET /stock-counts/{id}              → session + lines + variance
    approve POST /stock-counts/{id}/approve      → post adjustments atomically

Mounted under ``/api/v1/production`` alongside the single-shot stock-adjustments
endpoint so the whole inventory surface shares one namespace. Owner-scoped on every
read/write (SEC-02): a client can only see and drive their own stocktakes.
"""
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.auth import get_current_user
from dependencies.tenancy import get_owner_id
from models.branches import Branches
from models.clients import Clients
from models.products import Products
from models.stock_counts import Stock_count_lines, Stock_count_sessions
from schemas.auth import UserResponse
from services.production import fire_event_background
from services.stocktake import (
    approve_session,
    freeze_session,
    resolve_system_quantity,
    session_to_dict,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/production", tags=["production"])


# =============================================================================
# Schemas
# =============================================================================
class StartStocktakeRequest(BaseModel):
    # Null ⇒ a client-level stocktake; otherwise the per-branch ledger is counted.
    branch_id: Optional[int] = None
    name: Optional[str] = None
    note: Optional[str] = None


class StocktakeCountRequest(BaseModel):
    # Either a product_id (preferred) or a scanned barcode (resolved within client).
    product_id: Optional[int] = None
    barcode: Optional[str] = None
    counted_quantity: int
    note: Optional[str] = None


# =============================================================================
# Helpers
# =============================================================================
async def _resolve_client(db: AsyncSession, owner_id: str) -> Clients:
    client = (
        await db.execute(select(Clients).where(Clients.user_id == owner_id))
    ).scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=403, detail="Only clients can run a stocktake")
    return client


async def _load_session(
    db: AsyncSession, owner_id: str, session_id: int
) -> Stock_count_sessions:
    session = (
        await db.execute(
            select(Stock_count_sessions).where(
                Stock_count_sessions.id == session_id,
                Stock_count_sessions.user_id == owner_id,
            )
        )
    ).scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Stocktake not found")
    return session


async def _session_lines(db: AsyncSession, session_id: int):
    return (
        await db.execute(
            select(Stock_count_lines)
            .where(Stock_count_lines.session_id == session_id)
            .order_by(Stock_count_lines.product_name, Stock_count_lines.id)
        )
    ).scalars().all()


# =============================================================================
# Endpoints
# =============================================================================
@router.post("/stock-counts")
async def start_stocktake(
    data: StartStocktakeRequest,
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Start a guided stocktake — a resumable draft session (M4, #207)."""
    client = await _resolve_client(db, owner_id)

    if data.branch_id is not None:
        branch = (
            await db.execute(
                select(Branches).where(
                    Branches.user_id == owner_id,
                    Branches.id == int(data.branch_id),
                )
            )
        ).scalar_one_or_none()
        if not branch:
            raise HTTPException(status_code=404, detail="Branch not found")

    session = Stock_count_sessions(
        user_id=owner_id,
        client_id=client.id,
        branch_id=int(data.branch_id) if data.branch_id is not None else None,
        name=(data.name or "").strip() or None,
        note=(data.note or "").strip() or None,
        status="draft",
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session_to_dict(session, lines=[])


@router.get("/stock-counts")
async def list_stocktakes(
    status: Optional[str] = None,
    branch_id: Optional[int] = None,
    limit: int = 100,
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """List the caller's stocktakes, newest first (resumable drafts included)."""
    query = select(Stock_count_sessions).where(Stock_count_sessions.user_id == owner_id)
    if (status or "").strip():
        query = query.where(Stock_count_sessions.status == status.strip())
    if branch_id is not None:
        query = query.where(Stock_count_sessions.branch_id == int(branch_id))
    query = query.order_by(Stock_count_sessions.id.desc()).limit(max(1, min(int(limit), 500)))

    rows = (await db.execute(query)).scalars().all()
    return {"items": [session_to_dict(r) for r in rows], "total": len(rows)}


@router.get("/stock-counts/{session_id}")
async def get_stocktake(
    session_id: int,
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Fetch a stocktake with its lines + the computed variance (the review step)."""
    session = await _load_session(db, owner_id, session_id)
    lines = await _session_lines(db, session_id)
    return session_to_dict(session, lines=lines)


@router.post("/stock-counts/{session_id}/freeze")
async def freeze_stocktake(
    session_id: int,
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Freeze the on-hand baseline: snapshot every active product into a line.

    Transitions ``draft → frozen``. Idempotent under concurrency (a double-freeze
    snapshots once). Counting is only accepted once a session is frozen.
    """
    session = await _load_session(db, owner_id, session_id)
    if session.status != "draft":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot freeze a stocktake in '{session.status}' state",
        )

    products = (
        await db.execute(
            select(Products).where(
                Products.client_id == session.client_id,
                Products.is_active.isnot(False),
            )
        )
    ).scalars().all()

    created = await freeze_session(db, session, list(products))
    await db.commit()
    await db.refresh(session)
    lines = await _session_lines(db, session_id)
    logger.info("[STOCKTAKE] froze session=%s lines=%s", session_id, created)
    return session_to_dict(session, lines=lines)


@router.post("/stock-counts/{session_id}/count")
async def count_stocktake_line(
    session_id: int,
    data: StocktakeCountRequest,
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Record a barcode/manual count for one product (the counting step).

    Upserts the product's line (re-scanning overwrites the prior count, so the count
    is resumable and correctable) and recomputes its variance. Only accepted while
    the session is frozen.
    """
    session = await _load_session(db, owner_id, session_id)
    if session.status != "frozen":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot count a stocktake in '{session.status}' state — freeze it first",
        )

    counted = int(data.counted_quantity)
    if counted < 0:
        raise HTTPException(status_code=400, detail="Counted quantity cannot be negative")

    # Resolve the product within the caller's client scope (by id, else by barcode).
    prod_query = select(Products).where(Products.client_id == session.client_id)
    if data.product_id is not None:
        prod_query = prod_query.where(Products.id == int(data.product_id))
    elif (data.barcode or "").strip():
        prod_query = prod_query.where(Products.barcode == data.barcode.strip())
    else:
        raise HTTPException(status_code=400, detail="A product_id or barcode is required")
    product = (await db.execute(prod_query)).scalars().first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    line = (
        await db.execute(
            select(Stock_count_lines).where(
                Stock_count_lines.session_id == session_id,
                Stock_count_lines.product_id == product.id,
            )
        )
    ).scalar_one_or_none()

    # A product created after the freeze has no line yet — snapshot it now so its
    # count still lands (its baseline is the current on-hand).
    if line is None:
        system_qty = await resolve_system_quantity(
            db, session.client_id, session.branch_id, product
        )
        line = Stock_count_lines(
            session_id=session_id,
            user_id=owner_id,
            client_id=session.client_id,
            product_id=product.id,
            product_name=product.name,
            system_quantity=system_qty,
        )
        db.add(line)

    line.counted_quantity = counted
    line.variance = counted - int(line.system_quantity or 0)
    line.counted_at = datetime.now()
    if (data.note or "").strip():
        line.note = data.note.strip()

    await db.commit()
    await db.refresh(line)
    return {
        "id": line.id,
        "session_id": session_id,
        "product_id": line.product_id,
        "product_name": line.product_name,
        "system_quantity": line.system_quantity,
        "counted_quantity": line.counted_quantity,
        "variance": line.variance,
        "counted_at": line.counted_at.isoformat() if line.counted_at else None,
    }


@router.post("/stock-counts/{session_id}/approve")
async def approve_stocktake(
    session_id: int,
    background_tasks: BackgroundTasks,
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Approve a stocktake: post one adjustment per counted line, atomically.

    Sets each counted product's stock pool to its counted figure and writes a
    ``stock_adjustments`` variance row (reason ``count``) — all in one transaction.
    Idempotent under concurrency (a double-approve never double-posts). Uncounted
    lines are left untouched.
    """
    session = await _load_session(db, owner_id, session_id)
    if session.status != "frozen":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot approve a stocktake in '{session.status}' state",
        )

    won, summary = await approve_session(db, owner_id, session)
    if not won:
        # Lost the race / repeat — reflect the settled state without double-posting.
        await db.rollback()
        session = await _load_session(db, owner_id, session_id)
        raise HTTPException(
            status_code=409,
            detail=f"Stocktake is already '{session.status}'",
        )

    await db.commit()
    await db.refresh(session)

    # One summary webhook for the whole count (a per-line fan-out would be noisy).
    background_tasks.add_task(
        fire_event_background,
        owner_id,
        "inventory.updated",
        {
            "source": "stocktake",
            "session_id": session.id,
            "branch_id": session.branch_id,
            "adjustments_posted": summary.get("adjustments_posted", 0),
            "total_variance": summary.get("total_variance", 0),
        },
    )

    lines = await _session_lines(db, session_id)
    result = session_to_dict(session, lines=lines)
    result.update(summary)
    return result


@router.post("/stock-counts/{session_id}/cancel")
async def cancel_stocktake(
    session_id: int,
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Discard a draft/frozen stocktake without posting anything (no stock change)."""
    session = await _load_session(db, owner_id, session_id)
    if session.status not in ("draft", "frozen"):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot cancel a stocktake in '{session.status}' state",
        )
    await db.execute(
        update(Stock_count_sessions)
        .where(
            Stock_count_sessions.id == session_id,
            Stock_count_sessions.status.in_(("draft", "frozen")),
        )
        .values(status="cancelled")
    )
    await db.commit()
    await db.refresh(session)
    return session_to_dict(session)
