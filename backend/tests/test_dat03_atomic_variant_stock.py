"""DAT-03 — atomic conditional decrement for *variant* stock.

``deduct_variant_inventory`` must decrement ``product_variants.quantity`` with a
single conditional UPDATE (``... WHERE quantity >= :q``) + rowcount check, like
DAT-01/DAT-02 did for the client-level and per-branch stock — so N concurrent
variant sales on stock=K let *exactly* K succeed, with no read-check-write
oversell race.
"""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from conftest import add_product, make_client_account
from core.database import db_manager
from models.product_variants import Product_variants
from services.product_variants import deduct_variant_inventory


def _line(variant_id: int, quantity: float):
    return SimpleNamespace(variant_id=variant_id, product_id=None, quantity=quantity)


async def _seed_variant(
    user_id: str, client_id: int, product_id: int, qty: int, name: str = "Red / L"
) -> int:
    async with db_manager.async_session_maker() as db:
        variant = Product_variants(
            user_id=str(user_id),
            client_id=client_id,
            product_id=product_id,
            name=name,
            quantity=qty,
            price=10.0,
            is_active=True,
        )
        db.add(variant)
        await db.commit()
        await db.refresh(variant)
        return variant.id


async def _variant_qty(variant_id: int) -> int:
    async with db_manager.async_session_maker() as db:
        return (
            await db.execute(
                select(Product_variants.quantity).where(Product_variants.id == variant_id)
            )
        ).scalar_one()


async def _sell_one(client_id: int, variant_id: int) -> bool:
    """Run a single one-unit variant deduction in its own transaction."""
    async with db_manager.async_session_maker() as db:
        try:
            await deduct_variant_inventory(db, client_id, [_line(variant_id, 1)], False)
            await db.commit()
            return True
        except HTTPException:
            await db.rollback()
            return False


async def test_concurrent_variant_sales_do_not_oversell(client):
    """K=5 units on a variant, N=20 parallel one-unit sales -> exactly 5 succeed."""
    user, token, client_id = await make_client_account(client)
    pid = await add_product(client_id, user["id"], name="T-Shirt", quantity=999, price=10.0)
    vid = await _seed_variant(user["id"], client_id, pid, 5)

    results = await asyncio.gather(*[_sell_one(client_id, vid) for _ in range(20)])

    assert sum(results) == 5
    assert await _variant_qty(vid) == 0


async def test_variant_insufficient_stock_raises_and_leaves_stock_untouched(client):
    user, token, client_id = await make_client_account(client)
    pid = await add_product(client_id, user["id"], name="Hoodie", quantity=999, price=5.0)
    vid = await _seed_variant(user["id"], client_id, pid, 2, name="Blue / S")

    async with db_manager.async_session_maker() as db:
        with pytest.raises(HTTPException) as exc:
            await deduct_variant_inventory(db, client_id, [_line(vid, 10)], False)
        assert exc.value.status_code == 400
        await db.rollback()

    assert await _variant_qty(vid) == 2


async def test_variant_allow_negative_stock_goes_below_zero(client):
    user, token, client_id = await make_client_account(client)
    pid = await add_product(client_id, user["id"], name="Cap", quantity=999, price=2.0)
    vid = await _seed_variant(user["id"], client_id, pid, 1, name="One Size")

    async with db_manager.async_session_maker() as db:
        await deduct_variant_inventory(db, client_id, [_line(vid, 5)], True)
        await db.commit()

    assert await _variant_qty(vid) == -4
