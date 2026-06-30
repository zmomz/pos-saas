"""Per-branch price overrides (#220 multi-branch: branch-level pricing).

The product's client-level ``products.price`` is the chain-wide default. A branch
may override it for a product; absent an override the base price applies. Every
read/write is scoped to the caller's ``client_id`` (SEC-02), so one tenant's
branch prices never leak into another's.
"""
import logging
from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.product_branch_price import Product_branch_price
from models.products import Products

logger = logging.getLogger(__name__)


async def _get_row(
    db: AsyncSession, client_id: int, branch_id: int, product_id: int
) -> Optional[Product_branch_price]:
    return (
        await db.execute(
            select(Product_branch_price).where(
                Product_branch_price.client_id == client_id,
                Product_branch_price.branch_id == branch_id,
                Product_branch_price.product_id == product_id,
            )
        )
    ).scalar_one_or_none()


async def set_branch_price(
    db: AsyncSession, user_id: str, client_id: int, branch_id: int, product_id: int, price: float
) -> Product_branch_price:
    """Upsert a branch price override for one product (commits).

    One row per (client_id, branch_id, product_id): a second set updates the
    existing row's price rather than inserting a duplicate.
    """
    row = await _get_row(db, client_id, branch_id, product_id)
    if row is None:
        row = Product_branch_price(
            user_id=str(user_id),
            client_id=client_id,
            branch_id=branch_id,
            product_id=product_id,
            price=max(0.0, float(price)),
        )
        db.add(row)
    else:
        await db.execute(
            update(Product_branch_price)
            .where(Product_branch_price.id == row.id)
            .values(price=max(0.0, float(price)))
        )
    await db.commit()
    await db.refresh(row)
    return row


async def delete_branch_price(
    db: AsyncSession, client_id: int, branch_id: int, product_id: int
) -> bool:
    """Remove a branch override so the product falls back to the base price."""
    row = await _get_row(db, client_id, branch_id, product_id)
    if row is None:
        return False
    await db.delete(row)
    await db.commit()
    return True


async def list_branch_prices(
    db: AsyncSession, client_id: int, branch_id: int
) -> List[Product_branch_price]:
    return list(
        (
            await db.execute(
                select(Product_branch_price).where(
                    Product_branch_price.client_id == client_id,
                    Product_branch_price.branch_id == branch_id,
                )
            )
        ).scalars().all()
    )


async def resolve_price(
    db: AsyncSession, client_id: int, branch_id: int, product_id: int
) -> Optional[dict]:
    """Resolve the effective price for a product at a branch.

    Returns ``{"product_id", "branch_id", "price", "is_override"}``: the branch
    override price when one exists, else the product's chain-wide base price.
    Returns ``None`` when the product does not belong to the tenant.
    """
    product = (
        await db.execute(
            select(Products).where(
                Products.id == product_id, Products.client_id == client_id
            )
        )
    ).scalar_one_or_none()
    if product is None:
        return None

    row = await _get_row(db, client_id, branch_id, product_id)
    if row is not None:
        return {
            "product_id": product_id,
            "branch_id": branch_id,
            "price": row.price,
            "is_override": True,
        }
    return {
        "product_id": product_id,
        "branch_id": branch_id,
        "price": product.price,
        "is_override": False,
    }
