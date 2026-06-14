"""Per-branch *variant* stock ledger operations (ISSUE-067, INV-03 × INV-04).

Mirrors :mod:`services.branch_stock` but for product variants. All functions
operate within the caller's DB session and do **not** commit — the POS sale path
commits the branch-variant deductions atomically with the sale, exactly like the
client-level variant ledger (:func:`services.product_variants.deduct_variant_inventory`).
"""
import logging
from typing import Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.product_variants import Product_variants
from models.variant_branch_stock import Variant_branch_stock

logger = logging.getLogger(__name__)


def _variant_lines(items: List) -> Dict[int, float]:
    """Aggregate requested quantities per ``variant_id`` across cart/refund lines.

    Accepts Pydantic cart items (``.variant_id`` / ``.quantity``) or plain dicts
    (a voided/refunded ``items_json`` line). Lines with no ``variant_id`` are
    ignored — they decrement product/branch stock on the normal path.
    """
    requested: Dict[int, float] = {}
    for item in items:
        if isinstance(item, dict):
            vid = item.get("variant_id")
            qty = item.get("quantity") or 0
        else:
            vid = getattr(item, "variant_id", None)
            qty = getattr(item, "quantity", 0) or 0
        if not vid:
            continue
        requested[int(vid)] = requested.get(int(vid), 0.0) + float(qty)
    return requested


async def _get_row(
    db: AsyncSession, client_id: int, branch_id: int, variant_id: int
) -> Optional[Variant_branch_stock]:
    return (
        await db.execute(
            select(Variant_branch_stock).where(
                Variant_branch_stock.client_id == client_id,
                Variant_branch_stock.branch_id == branch_id,
                Variant_branch_stock.variant_id == variant_id,
            )
        )
    ).scalar_one_or_none()


async def get_or_init_row(
    db: AsyncSession, user_id: str, client_id: int, branch_id: int, variant: Product_variants
) -> Variant_branch_stock:
    """Return the branch-variant row, seeding it from the variant's client-level
    quantity the first time the branch transacts this variant."""
    row = await _get_row(db, client_id, branch_id, variant.id)
    if row is None:
        row = Variant_branch_stock(
            user_id=str(user_id),
            client_id=client_id,
            branch_id=branch_id,
            variant_id=variant.id,
            quantity=variant.quantity or 0,
        )
        db.add(row)
        await db.flush()
    return row


async def deduct_variant_branch_inventory(
    db: AsyncSession,
    user_id: str,
    client_id: int,
    branch_id: int,
    items: List,
    allow_negative_stock: bool,
) -> None:
    """Decrement per-branch variant stock for the sold variant lines (no commit).

    Raises ``HTTPException(400)`` on insufficient branch-variant stock unless
    overselling is allowed. A variant_id that does not map to one of this client's
    variants is skipped (SEC-02), so a stale/foreign variant can't deduct another
    tenant's stock.
    """
    for variant_id, qty in _variant_lines(items).items():
        variant = (
            await db.execute(
                select(Product_variants).where(
                    Product_variants.id == variant_id,
                    Product_variants.client_id == client_id,
                )
            )
        ).scalar_one_or_none()
        if not variant:
            continue

        row = await get_or_init_row(db, user_id, client_id, branch_id, variant)
        available = row.quantity or 0
        if not allow_negative_stock and available < qty:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Insufficient stock for variant '{variant.name}' at this branch: "
                    f"requested {int(qty)}, available {int(available)}"
                ),
            )
        new_qty = available - qty
        if not allow_negative_stock:
            new_qty = max(0, new_qty)
        row.quantity = new_qty


async def restore_variant_branch_inventory(
    db: AsyncSession, user_id: str, client_id: int, branch_id: int, items: List
) -> None:
    """Add quantities back to per-branch variant stock (inverse of deduction; no commit)."""
    for variant_id, qty in _variant_lines(items).items():
        variant = (
            await db.execute(
                select(Product_variants).where(
                    Product_variants.id == variant_id,
                    Product_variants.client_id == client_id,
                )
            )
        ).scalar_one_or_none()
        if not variant:
            continue
        row = await get_or_init_row(db, user_id, client_id, branch_id, variant)
        row.quantity = (row.quantity or 0) + qty


async def set_variant_branch_stock(
    db: AsyncSession, user_id: str, client_id: int, branch_id: int, variant_id: int, quantity: int
) -> Variant_branch_stock:
    """Upsert a branch-variant stock allocation (commits)."""
    row = await _get_row(db, client_id, branch_id, variant_id)
    if row is None:
        row = Variant_branch_stock(
            user_id=str(user_id),
            client_id=client_id,
            branch_id=branch_id,
            variant_id=variant_id,
            quantity=max(0, quantity),
        )
        db.add(row)
    else:
        await db.execute(
            update(Variant_branch_stock)
            .where(Variant_branch_stock.id == row.id)
            .values(quantity=max(0, quantity))
        )
    await db.commit()
    await db.refresh(row)
    return row


async def list_variant_branch_stock(
    db: AsyncSession, client_id: int, branch_id: int
) -> List[Variant_branch_stock]:
    return list(
        (
            await db.execute(
                select(Variant_branch_stock).where(
                    Variant_branch_stock.client_id == client_id,
                    Variant_branch_stock.branch_id == branch_id,
                )
            )
        ).scalars().all()
    )
