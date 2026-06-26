"""DAT-01 — atomic conditional decrement for primary product stock.

``deduct_inventory`` must decrement ``Products.quantity`` with a single
conditional UPDATE (``... WHERE quantity >= :q``) + rowcount check so that N
concurrent sales on stock=K let *exactly* K succeed — no read-check-write
oversell race.
"""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from conftest import add_product, get_product_quantity, make_client_account
from core.database import db_manager
from services.sale_core import deduct_inventory


def _line(product_id: int, quantity: float):
    return SimpleNamespace(product_id=product_id, quantity=quantity)


async def _sell_one(client_id: int, product_id: int) -> bool:
    """Run a single one-unit deduction in its own transaction. True if it sold."""
    async with db_manager.async_session_maker() as db:
        try:
            await deduct_inventory(db, client_id, [_line(product_id, 1)], False)
            await db.commit()
            return True
        except HTTPException:
            await db.rollback()
            return False


async def test_concurrent_sales_do_not_oversell(client):
    """K=5 units, N=20 parallel one-unit sales -> exactly 5 succeed, stock hits 0."""
    user, token, client_id = await make_client_account(client)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=5, price=10.0)

    results = await asyncio.gather(*[_sell_one(client_id, pid) for _ in range(20)])

    assert sum(results) == 5
    assert await get_product_quantity(pid) == 0


async def test_insufficient_stock_raises_and_leaves_stock_untouched(client):
    user, token, client_id = await make_client_account(client)
    pid = await add_product(client_id, user["id"], name="Juice", quantity=2, price=5.0)

    async with db_manager.async_session_maker() as db:
        with pytest.raises(HTTPException) as exc:
            await deduct_inventory(db, client_id, [_line(pid, 10)], False)
        assert exc.value.status_code == 400
        await db.rollback()

    assert await get_product_quantity(pid) == 2


async def test_allow_negative_stock_goes_below_zero(client):
    user, token, client_id = await make_client_account(client)
    pid = await add_product(client_id, user["id"], name="Loose", quantity=1, price=2.0)

    async with db_manager.async_session_maker() as db:
        await deduct_inventory(db, client_id, [_line(pid, 5)], True)
        await db.commit()

    assert await get_product_quantity(pid) == -4


async def test_unknown_product_is_skipped(client):
    """An ad-hoc line whose product_id isn't owned by the client deducts nothing."""
    user, token, client_id = await make_client_account(client)

    async with db_manager.async_session_maker() as db:
        # Should not raise even though product 999999 doesn't exist.
        await deduct_inventory(db, client_id, [_line(999999, 3)], False)
        await db.commit()
