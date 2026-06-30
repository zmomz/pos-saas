"""Shared catalog management across branches (#220 multi-branch).

A multi-location chain manages one shared product catalog. By default every active
chain product is available at every branch (permissive; single-branch installs are
unaffected). A branch may opt a product *out* of its local catalog; resolving a
branch's effective catalog returns all active chain products minus the ones that
branch has disabled. Every read/write is scoped to the caller's ``client_id``
(SEC-02), so one tenant's branch overrides never leak into another's.

Sale-time enforcement (rejecting a line for a product a branch has opted out of) is
the "then expand" follow-up; this service resolves the effective catalog only,
mirroring ``branch_promotions`` / ``branch_pricing`` / ``branch_tax``.
"""
import logging
from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.branch_catalog_override import Branch_catalog_override
from models.products import Products

logger = logging.getLogger(__name__)


async def _get_row(
    db: AsyncSession, client_id: int, branch_id: int, product_id: int
) -> Optional[Branch_catalog_override]:
    return (
        await db.execute(
            select(Branch_catalog_override).where(
                Branch_catalog_override.client_id == client_id,
                Branch_catalog_override.branch_id == branch_id,
                Branch_catalog_override.product_id == product_id,
            )
        )
    ).scalar_one_or_none()


async def set_branch_catalog(
    db: AsyncSession,
    user_id: str,
    client_id: int,
    branch_id: int,
    product_id: int,
    is_available: bool,
) -> Branch_catalog_override:
    """Upsert a branch's availability of one shared product (commits).

    One row per (client_id, branch_id, product_id): a second set updates the
    existing row's ``is_available`` flag rather than inserting a duplicate, so
    re-stocking a previously opted-out product toggles the same row.
    """
    row = await _get_row(db, client_id, branch_id, product_id)
    if row is None:
        row = Branch_catalog_override(
            user_id=str(user_id),
            client_id=client_id,
            branch_id=branch_id,
            product_id=product_id,
            is_available=bool(is_available),
        )
        db.add(row)
    else:
        await db.execute(
            update(Branch_catalog_override)
            .where(Branch_catalog_override.id == row.id)
            .values(is_available=bool(is_available))
        )
    await db.commit()
    await db.refresh(row)
    return row


async def delete_branch_catalog(
    db: AsyncSession, client_id: int, branch_id: int, product_id: int
) -> bool:
    """Remove a branch override so the product falls back to available."""
    row = await _get_row(db, client_id, branch_id, product_id)
    if row is None:
        return False
    await db.delete(row)
    await db.commit()
    return True


async def _disabled_product_ids(
    db: AsyncSession, client_id: int, branch_id: int
) -> set:
    rows = (
        await db.execute(
            select(Branch_catalog_override.product_id).where(
                Branch_catalog_override.client_id == client_id,
                Branch_catalog_override.branch_id == branch_id,
                Branch_catalog_override.is_available.is_(False),
            )
        )
    ).scalars().all()
    return {int(pid) for pid in rows}


async def resolve_branch_catalog(
    db: AsyncSession, client_id: int, branch_id: int
) -> dict:
    """Resolve the catalog effective at a branch.

    Returns ``{"branch_id", "products", "disabled_product_ids"}``: every active
    chain product (owner-scoped, SEC-02) the branch has *not* opted out of, plus
    the sorted list of product ids the branch has disabled. ``products`` is a list
    of ``{product_id, name}`` summaries ordered by product id.
    """
    disabled = await _disabled_product_ids(db, client_id, branch_id)
    active = (
        await db.execute(
            select(Products.id, Products.name)
            .where(
                Products.client_id == client_id,
                Products.is_active.isnot(False),
            )
            .order_by(Products.id)
        )
    ).all()
    products = [
        {"product_id": pid, "name": name}
        for pid, name in active
        if int(pid) not in disabled
    ]
    return {
        "branch_id": branch_id,
        "products": products,
        "disabled_product_ids": sorted(disabled),
    }
