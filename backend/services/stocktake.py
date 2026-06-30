"""Guided stocktake service — freeze snapshot + atomic approval (M4, #207).

Sits on top of the ``stock_adjustments`` variance primitive (INV-06): a stocktake
session freezes the on-hand baseline across a branch, accepts barcode counts against
it, and on approval posts one ``stock_adjustments`` row per counted line while
setting each stock pool to its counted figure — all in the caller's transaction so a
whole count lands (or rolls back) atomically.

Like :mod:`services.branch_stock`, these helpers operate within the caller's session
and do **not** commit; the router commits once so the freeze/approve and their side
effects are atomic.
"""
import logging
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.product_branch_stock import Product_branch_stock
from models.products import Products
from models.stock_adjustments import Stock_adjustments
from models.stock_counts import Stock_count_lines, Stock_count_sessions
from services.branch_stock import get_or_init_row

logger = logging.getLogger(__name__)


async def resolve_system_quantity(
    db: AsyncSession, client_id: int, branch_id: Optional[int], product: Products
) -> int:
    """The on-hand the count is measured against, read-only.

    For a branch session it's the per-branch ledger figure (falling back to the
    product's client-level quantity the same way the ledger lazily seeds), so freeze
    never mass-inserts branch rows; for a client session it's ``products.quantity``.
    """
    if branch_id is None:
        return int(product.quantity or 0)
    row = (
        await db.execute(
            select(Product_branch_stock.quantity).where(
                Product_branch_stock.client_id == client_id,
                Product_branch_stock.branch_id == branch_id,
                Product_branch_stock.product_id == product.id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return int(product.quantity or 0)
    return int(row or 0)


async def freeze_session(
    db: AsyncSession, session: Stock_count_sessions, products: List[Products]
) -> int:
    """Snapshot every active product's on-hand into the session's lines (no commit).

    Gates the ``draft → frozen`` transition with a single conditional UPDATE so a
    concurrent double-freeze snapshots once. Returns the number of lines created (0
    if this caller lost the race / the session was not a draft).
    """
    now = datetime.now()
    gate = await db.execute(
        update(Stock_count_sessions)
        .where(
            Stock_count_sessions.id == session.id,
            Stock_count_sessions.status == "draft",
        )
        .values(status="frozen", frozen_at=now)
    )
    if not gate.rowcount:
        return 0

    for product in products:
        system_qty = await resolve_system_quantity(
            db, session.client_id, session.branch_id, product
        )
        db.add(
            Stock_count_lines(
                session_id=session.id,
                user_id=session.user_id,
                client_id=session.client_id,
                product_id=product.id,
                product_name=product.name,
                system_quantity=system_qty,
                counted_quantity=None,
                variance=None,
            )
        )
    return len(products)


async def approve_session(
    db: AsyncSession, owner_id: str, session: Stock_count_sessions
) -> Tuple[bool, dict]:
    """Post adjustments for every counted line atomically (no commit).

    Gates ``frozen → approved`` with a single conditional UPDATE — only the caller
    that flips the row posts, so a double-approve never double-posts. For each
    counted line it sets the stock pool (per-branch ledger when the session is
    branch-scoped, else ``products.quantity``) to the counted figure and writes one
    ``stock_adjustments`` variance row (reason ``count``). Uncounted lines are left
    untouched — never zeroed.

    Returns ``(won, summary)``; ``won`` is False (empty summary) when the session
    was already approved / not frozen (this caller lost the race or repeated).
    """
    now = datetime.now()
    gate = await db.execute(
        update(Stock_count_sessions)
        .where(
            Stock_count_sessions.id == session.id,
            Stock_count_sessions.status == "frozen",
        )
        .values(status="approved", approved_at=now)
    )
    if not gate.rowcount:
        return False, {}

    lines = (
        await db.execute(
            select(Stock_count_lines).where(
                Stock_count_lines.session_id == session.id,
                Stock_count_lines.counted_quantity.isnot(None),
            )
        )
    ).scalars().all()

    posted = 0
    total_variance = 0
    for line in lines:
        counted = int(line.counted_quantity)
        product = (
            await db.execute(
                select(Products).where(
                    Products.id == line.product_id,
                    Products.client_id == session.client_id,
                )
            )
        ).scalar_one_or_none()
        if product is None:
            # Product deleted between freeze and approve — skip; nothing to post to.
            continue

        if session.branch_id is not None:
            row = await get_or_init_row(
                db, owner_id, session.client_id, session.branch_id, product
            )
            system_quantity = int(row.quantity or 0)
            await db.execute(
                update(Product_branch_stock)
                .where(Product_branch_stock.id == row.id)
                .values(quantity=counted)
            )
        else:
            system_quantity = int(product.quantity or 0)
            product.quantity = counted

        # The variance posted reflects on-hand the moment of approval (the pool may
        # have moved since freeze); the count is authoritative — physical wins.
        variance = counted - system_quantity
        db.add(
            Stock_adjustments(
                user_id=owner_id,
                client_id=session.client_id,
                branch_id=session.branch_id,
                product_id=product.id,
                product_name=product.name,
                reason="count",
                system_quantity=system_quantity,
                counted_quantity=counted,
                variance=variance,
                note=f"Stocktake #{session.id}",
            )
        )
        posted += 1
        total_variance += variance

    return True, {
        "session_id": session.id,
        "adjustments_posted": posted,
        "total_variance": total_variance,
    }


def line_to_dict(line: Stock_count_lines) -> dict:
    return {
        "id": line.id,
        "product_id": line.product_id,
        "product_name": line.product_name,
        "system_quantity": line.system_quantity,
        "counted_quantity": line.counted_quantity,
        "variance": line.variance,
        "counted": line.counted_quantity is not None,
        "note": line.note,
        "counted_at": line.counted_at.isoformat() if line.counted_at else None,
    }


def session_to_dict(session: Stock_count_sessions, lines: Optional[List] = None) -> dict:
    out = {
        "id": session.id,
        "branch_id": session.branch_id,
        "name": session.name,
        "status": session.status,
        "note": session.note,
        "frozen_at": session.frozen_at.isoformat() if session.frozen_at else None,
        "approved_at": session.approved_at.isoformat() if session.approved_at else None,
        "created_at": session.created_at.isoformat() if session.created_at else None,
    }
    if lines is not None:
        dict_lines = [line_to_dict(line) for line in lines]
        counted = [line for line in dict_lines if line["counted"]]
        out["lines"] = dict_lines
        out["line_count"] = len(dict_lines)
        out["counted_count"] = len(counted)
        out["variance_count"] = sum(1 for line in counted if (line["variance"] or 0) != 0)
        out["total_variance"] = sum(line["variance"] or 0 for line in counted)
    return out
