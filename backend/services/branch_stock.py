"""Per-branch stock ledger operations (Phase 6 multi-branch completeness).

All functions operate within the caller's DB session and do **not** commit — the
POS sale path commits the branch deductions atomically with the sale, exactly
like the client-level :func:`routers.pos._deduct_inventory`.
"""
import logging
from typing import Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import func, select, update
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
    requested: Dict[int, float] = {}
    for item in items:
        requested[item.product_id] = requested.get(item.product_id, 0) + item.quantity

    for product_id, qty in requested.items():
        qty = float(qty)
        product = (
            await db.execute(
                select(Products).where(
                    Products.id == product_id, Products.client_id == client_id
                )
            )
        ).scalar_one_or_none()
        if not product:
            continue

        # Ensure the branch-stock row exists (seeded from the product's client-level
        # quantity the first time this branch transacts the product).
        row = await get_or_init_row(db, user_id, client_id, branch_id, product)

        # DAT-02: decrement with one conditional UPDATE on the branch-stock row
        # (mirrors DAT-01 on Products). The ``quantity >= qty`` guard (dropped when
        # overselling is allowed) makes the check-and-decrement a single atomic
        # statement, so N concurrent branch sales on stock=K let exactly K succeed —
        # no read-check-write oversell race. COALESCE treats a NULL on-hand as 0.
        stmt = (
            update(Product_branch_stock)
            .where(Product_branch_stock.id == row.id)
            .values(quantity=func.coalesce(Product_branch_stock.quantity, 0) - qty)
        )
        if not allow_negative_stock:
            stmt = stmt.where(func.coalesce(Product_branch_stock.quantity, 0) >= qty)

        result = await db.execute(stmt)
        if result.rowcount:
            continue

        # No row updated (and the row exists): not enough branch stock.
        available = row.quantity or 0
        raise HTTPException(
            status_code=400,
            detail=(
                f"Insufficient stock for '{product.name}' at this branch: "
                f"requested {qty}, available {available}"
            ),
        )


async def _conditional_decrement(
    db: AsyncSession,
    row: Product_branch_stock,
    qty: float,
    allow_negative_stock: bool,
) -> bool:
    """Atomically decrement one branch-stock row by ``qty`` with a single
    conditional UPDATE (``... WHERE quantity >= qty`` unless overselling is
    allowed). Returns True if the row was decremented, False if the guard
    rejected it (insufficient stock) — never a read-check-write."""
    stmt = (
        update(Product_branch_stock)
        .where(Product_branch_stock.id == row.id)
        .values(quantity=func.coalesce(Product_branch_stock.quantity, 0) - qty)
    )
    if not allow_negative_stock:
        stmt = stmt.where(func.coalesce(Product_branch_stock.quantity, 0) >= qty)
    return bool((await db.execute(stmt)).rowcount)


async def dispatch_branch_inventory(
    db: AsyncSession,
    user_id: str,
    client_id: int,
    from_branch_id: int,
    product: Products,
    qty: float,
    allow_negative_stock: bool = False,
) -> float:
    """Ship ``qty`` out of the source branch ledger (no commit) — phase 1 of a
    two-phase transfer. Conditional decrement on the source only (DAT-04); the
    destination is credited on receive. Raises HTTPException(400) when the source
    has insufficient stock. Returns the new source on-hand."""
    src = await get_or_init_row(db, user_id, client_id, from_branch_id, product)
    if not await _conditional_decrement(db, src, qty, allow_negative_stock):
        available = src.quantity or 0
        raise HTTPException(
            status_code=400,
            detail=(
                f"Insufficient stock for '{product.name}' at the source branch: "
                f"requested {qty}, available {available}"
            ),
        )
    await db.refresh(src)
    return src.quantity


async def transfer_branch_inventory(
    db: AsyncSession,
    user_id: str,
    client_id: int,
    from_branch_id: int,
    to_branch_id: int,
    product: Products,
    qty: float,
    allow_negative_stock: bool = False,
) -> tuple:
    """Move ``qty`` of ``product`` from one branch ledger to another (no commit).

    DAT-04: the source leg is a single conditional UPDATE
    (``... SET quantity = quantity - qty WHERE quantity >= qty``) and the
    destination leg a single atomic increment UPDATE — never a read-check-write.
    Both run in the caller's transaction, so the two legs land (or roll back)
    together and N concurrent transfers out of a branch holding K let *exactly* K
    succeed, with stock conserved (no double-move, no loss). The source guard is
    dropped when overselling is allowed. Raises HTTPException(400) when the source
    has insufficient stock. Returns ``(new_source_qty, new_dest_qty)``.
    """
    src = await get_or_init_row(db, user_id, client_id, from_branch_id, product)
    dst = await get_or_init_row(db, user_id, client_id, to_branch_id, product)

    if not await _conditional_decrement(db, src, qty, allow_negative_stock):
        # Source row exists (seeded above) but the guard rejected it: not enough stock.
        available = src.quantity or 0
        raise HTTPException(
            status_code=400,
            detail=(
                f"Insufficient stock for '{product.name}' at the source branch: "
                f"requested {qty}, available {available}"
            ),
        )

    await db.execute(
        update(Product_branch_stock)
        .where(Product_branch_stock.id == dst.id)
        .values(quantity=func.coalesce(Product_branch_stock.quantity, 0) + qty)
    )

    # Reflect the atomic writes on the ORM objects for the caller's response.
    await db.refresh(src)
    await db.refresh(dst)
    return src.quantity, dst.quantity


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
