"""DAT-02 — atomic conditional decrement for *branch* stock.

``deduct_branch_inventory`` must decrement ``product_branch_stock.quantity`` with
a single conditional UPDATE (``... WHERE quantity >= :q``) + rowcount check, like
DAT-01 did for the client-level product stock — so N concurrent branch sales on
stock=K let *exactly* K succeed, with no read-check-write oversell race.
"""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from conftest import add_product, make_client_account
from core.database import db_manager
from models.product_branch_stock import Product_branch_stock
from services.branch_stock import deduct_branch_inventory, set_branch_stock
from sqlalchemy import select

BRANCH_ID = 1


def _line(product_id: int, quantity: float):
    return SimpleNamespace(product_id=product_id, quantity=quantity)


async def _branch_qty(client_id: int, product_id: int) -> float:
    async with db_manager.async_session_maker() as db:
        row = (
            await db.execute(
                select(Product_branch_stock).where(
                    Product_branch_stock.client_id == client_id,
                    Product_branch_stock.branch_id == BRANCH_ID,
                    Product_branch_stock.product_id == product_id,
                )
            )
        ).scalar_one()
        return row.quantity


async def _sell_one(user_id: str, client_id: int, product_id: int) -> bool:
    """Run a single one-unit branch deduction in its own transaction."""
    async with db_manager.async_session_maker() as db:
        try:
            await deduct_branch_inventory(
                db, user_id, client_id, BRANCH_ID, [_line(product_id, 1)], False
            )
            await db.commit()
            return True
        except HTTPException:
            await db.rollback()
            return False


async def test_concurrent_branch_sales_do_not_oversell(client):
    """K=5 units at the branch, N=20 parallel one-unit sales -> exactly 5 succeed."""
    user, token, client_id = await make_client_account(client)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=999, price=10.0)
    # Allocate exactly 5 units to the branch ledger (independent of client-level qty).
    await _seed_branch(user["id"], client_id, pid, 5)

    results = await asyncio.gather(
        *[_sell_one(user["id"], client_id, pid) for _ in range(20)]
    )

    assert sum(results) == 5
    assert await _branch_qty(client_id, pid) == 0


async def test_branch_insufficient_stock_raises_and_leaves_stock_untouched(client):
    user, token, client_id = await make_client_account(client)
    pid = await add_product(client_id, user["id"], name="Juice", quantity=999, price=5.0)
    await _seed_branch(user["id"], client_id, pid, 2)

    async with db_manager.async_session_maker() as db:
        with pytest.raises(HTTPException) as exc:
            await deduct_branch_inventory(
                db, user["id"], client_id, BRANCH_ID, [_line(pid, 10)], False
            )
        assert exc.value.status_code == 400
        await db.rollback()

    assert await _branch_qty(client_id, pid) == 2


async def test_branch_allow_negative_stock_goes_below_zero(client):
    user, token, client_id = await make_client_account(client)
    pid = await add_product(client_id, user["id"], name="Loose", quantity=999, price=2.0)
    await _seed_branch(user["id"], client_id, pid, 1)

    async with db_manager.async_session_maker() as db:
        await deduct_branch_inventory(
            db, user["id"], client_id, BRANCH_ID, [_line(pid, 5)], True
        )
        await db.commit()

    assert await _branch_qty(client_id, pid) == -4


async def _seed_branch(user_id: str, client_id: int, product_id: int, qty: float):
    async with db_manager.async_session_maker() as db:
        await set_branch_stock(db, user_id, client_id, BRANCH_ID, product_id, qty)
