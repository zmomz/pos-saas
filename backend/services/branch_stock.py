"""Per-branch stock ledger operations (Phase 6 multi-branch completeness).

All functions operate within the caller's DB session and do **not** commit — the
POS sale path commits the branch deductions atomically with the sale, exactly
like the client-level :func:`routers.pos._deduct_inventory`.
"""
import logging
from typing import Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.product_branch_stock import Product_branch_stock
from models.products import Products

logger = logging.getLogger(__name__)


async def _get_row(
    db: AsyncSession, client_id: int, branch_id: int, product_id: int
) -> Optional[Product_branch_stock]:
    return (
        await db.execute(
            select(Product_branch_stock).where(
                Product_branch_stock.client_id == client_id,
                Product_branch_stock.branch_id == branch_id,
                Product_branch_stock.product_id == product_id,
            )
        )
    ).scalar_one_or_none()


async def get_or_init_row(
    db: AsyncSession, user_id: str, client_id: int, branch_id: int, product: Products
) -> Product_branch_stock:
    """Return the branch-stock row, seeding it from the product's client-level
    quantity the first time the branch transacts this product."""
    row = await _get_row(db, client_id, branch_id, product.id)
    if row is None:
        row = Product_branch_stock(
            user_id=str(user_id),
            client_id=client_id,
            branch_id=branch_id,
            product_id=product.id,
            quantity=product.quantity or 0,
        )
        db.add(row)
        await db.flush()
    return row


async def deduct_branch_inventory(
    db: AsyncSession,
    user_id: str,
    client_id: int,
    branch_id: int,
    items: List,
    allow_negative_stock: bool,
) -> None:
    """Decrement per-branch stock for the sold items (no commit).

    Raises HTTPException(400) on insufficient branch stock unless overselling is
    allowed. Unknown/ad-hoc product lines are skipped.
    """
    requested: Dict[int, int] = {}
    for item in items:
        requested[item.product_id] = requested.get(item.product_id, 0) + item.quantity

    for product_id, qty in requested.items():
        product = (
            await db.execute(
                select(Products).where(
                    Products.id == product_id, Products.client_id == client_id
                )
            )
        ).scalar_one_or_none()
        if not product:
            continue

        row = await get_or_init_row(db, user_id, client_id, branch_id, product)
        available = row.quantity or 0
        if not allow_negative_stock and available < qty:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Insufficient stock for '{product.name}' at this branch: "
                    f"requested {qty}, available {available}"
                ),
            )
        new_qty = available - qty
        if not allow_negative_stock:
            new_qty = max(0, new_qty)
        row.quantity = new_qty


async def restore_branch_inventory(
    db: AsyncSession,
    user_id: str,
    client_id: int,
    branch_id: int,
    items: List,
) -> None:
    """Add quantities back to per-branch stock (inverse of deduction; no commit)."""
    restore: Dict[int, int] = {}
    for item in items:
        pid = item.get("product_id") if isinstance(item, dict) else item.product_id
        q = item.get("quantity", 0) if isinstance(item, dict) else item.quantity
        if pid is None:
            continue
        restore[pid] = restore.get(pid, 0) + (q or 0)

    for product_id, qty in restore.items():
        product = (
            await db.execute(
                select(Products).where(
                    Products.id == product_id, Products.client_id == client_id
                )
            )
        ).scalar_one_or_none()
        if not product:
            continue
        row = await get_or_init_row(db, user_id, client_id, branch_id, product)
        row.quantity = (row.quantity or 0) + qty


async def set_branch_stock(
    db: AsyncSession, user_id: str, client_id: int, branch_id: int, product_id: int, quantity: int
) -> Product_branch_stock:
    """Upsert a branch-stock allocation (commits)."""
    row = await _get_row(db, client_id, branch_id, product_id)
    if row is None:
        row = Product_branch_stock(
            user_id=str(user_id),
            client_id=client_id,
            branch_id=branch_id,
            product_id=product_id,
            quantity=max(0, quantity),
        )
        db.add(row)
    else:
        await db.execute(
            update(Product_branch_stock)
            .where(Product_branch_stock.id == row.id)
            .values(quantity=max(0, quantity))
        )
    await db.commit()
    await db.refresh(row)
    return row


async def list_branch_stock(
    db: AsyncSession, client_id: int, branch_id: int
) -> List[Product_branch_stock]:
    return list(
        (
            await db.execute(
                select(Product_branch_stock).where(
                    Product_branch_stock.client_id == client_id,
                    Product_branch_stock.branch_id == branch_id,
                )
            )
        ).scalars().all()
    )
