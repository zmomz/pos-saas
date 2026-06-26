"""DAT-04 — atomic two-phase (inter-branch) stock transfer.

The branch-transfer path read-modify-wrote *both* ledger legs without locking
(read source on-hand, check, then write source− and dest+), so concurrent
transfers could double-move or lose stock — the same read-check-write race
DAT-02 fixed for branch *sales*.

``transfer_branch_inventory`` must move stock with a conditional decrement on the
source (rejected if insufficient) + an atomic increment on the destination, both
single UPDATE statements in one transaction. So N concurrent one-unit transfers
out of a branch holding K let *exactly* K succeed, total stock is conserved, and
an insufficient-source transfer is rejected without touching either leg.
"""
import asyncio

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from conftest import add_product, auth_headers, make_client_account
from models.stock_transfers import Stock_transfers
from core.database import db_manager
from models.product_branch_stock import Product_branch_stock
from models.products import Products
from services.branch_stock import set_branch_stock, transfer_branch_inventory

SRC_BRANCH = 1
DST_BRANCH = 2


async def _product(product_id: int) -> Products:
    async with db_manager.async_session_maker() as db:
        return (
            await db.execute(select(Products).where(Products.id == product_id))
        ).scalar_one()


async def _branch_qty(client_id: int, branch_id: int, product_id: int) -> float:
    async with db_manager.async_session_maker() as db:
        row = (
            await db.execute(
                select(Product_branch_stock).where(
                    Product_branch_stock.client_id == client_id,
                    Product_branch_stock.branch_id == branch_id,
                    Product_branch_stock.product_id == product_id,
                )
            )
        ).scalar_one_or_none()
        return (row.quantity if row else 0) or 0


async def _seed(user_id: str, client_id: int, branch_id: int, product_id: int, qty: float):
    async with db_manager.async_session_maker() as db:
        await set_branch_stock(db, user_id, client_id, branch_id, product_id, qty)


async def _transfer_one(user_id: str, client_id: int, product: Products) -> bool:
    """Run a single one-unit source→dest transfer in its own transaction."""
    async with db_manager.async_session_maker() as db:
        try:
            await transfer_branch_inventory(
                db, user_id, client_id, SRC_BRANCH, DST_BRANCH, product, 1, False
            )
            await db.commit()
            return True
        except HTTPException:
            await db.rollback()
            return False


async def test_concurrent_transfers_conserve_stock(client):
    """K=5 at the source, N=20 parallel one-unit transfers → exactly 5 move; total
    (source + dest) stays 5 — no double-move, no loss."""
    user, _token, client_id = await make_client_account(client)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=999, price=10.0)
    await _seed(user["id"], client_id, SRC_BRANCH, pid, 5)
    await _seed(user["id"], client_id, DST_BRANCH, pid, 0)
    product = await _product(pid)

    results = await asyncio.gather(
        *[_transfer_one(user["id"], client_id, product) for _ in range(20)]
    )

    assert sum(results) == 5
    src_qty = await _branch_qty(client_id, SRC_BRANCH, pid)
    dst_qty = await _branch_qty(client_id, DST_BRANCH, pid)
    assert src_qty == 0
    assert dst_qty == 5
    assert src_qty + dst_qty == 5  # stock conserved across the move


async def test_insufficient_source_rejected_and_legs_untouched(client):
    """A transfer larger than the source on-hand is a 400; neither the source nor
    the destination ledger moves."""
    user, _token, client_id = await make_client_account(client)
    pid = await add_product(client_id, user["id"], name="Juice", quantity=999, price=5.0)
    await _seed(user["id"], client_id, SRC_BRANCH, pid, 2)
    await _seed(user["id"], client_id, DST_BRANCH, pid, 7)
    product = await _product(pid)

    async with db_manager.async_session_maker() as db:
        with pytest.raises(HTTPException) as exc:
            await transfer_branch_inventory(
                db, user["id"], client_id, SRC_BRANCH, DST_BRANCH, product, 10, False
            )
        assert exc.value.status_code == 400
        await db.rollback()

    assert await _branch_qty(client_id, SRC_BRANCH, pid) == 2
    assert await _branch_qty(client_id, DST_BRANCH, pid) == 7


async def _make_branch(client, headers, name):
    resp = await client.post(
        "/api/v1/entities/branches", json={"name": name, "is_active": True}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _allocate(client, headers, branch_id, product_id, quantity):
    resp = await client.put(
        f"/api/v1/pos/branches/{branch_id}/stock",
        json={"product_id": product_id, "quantity": quantity},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text


async def test_one_step_transfer_endpoint_moves_stock_and_logs_moved_amount(client):
    """The wired one-step transfer endpoint moves N atomically and writes exactly
    one history row whose quantity equals the moved amount."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=0, price=10.0)
    src = await _make_branch(client, headers, "Main")
    dst = await _make_branch(client, headers, "Second")
    await _allocate(client, headers, src, pid, 40)
    await _allocate(client, headers, dst, pid, 10)

    resp = await client.post(
        "/api/v1/production/branches/transfer",
        json={"from_branch_id": src, "to_branch_id": dst, "product_id": pid, "quantity": 15},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["from_branch_quantity"] == 25
    assert body["to_branch_quantity"] == 25

    async with db_manager.async_session_maker() as db:
        rows = (
            await db.execute(
                select(Stock_transfers).where(Stock_transfers.client_id == client_id)
            )
        ).scalars().all()
    assert len(rows) == 1
    assert rows[0].quantity == 15  # history consistent with the moved amount
    assert rows[0].status == "received"


async def test_one_step_transfer_endpoint_rejects_oversell_without_history(client):
    """A transfer exceeding the source on-hand is a 400 and leaves no history row
    and both ledgers untouched."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=0, price=10.0)
    src = await _make_branch(client, headers, "Main")
    dst = await _make_branch(client, headers, "Second")
    await _allocate(client, headers, src, pid, 3)
    await _allocate(client, headers, dst, pid, 1)

    resp = await client.post(
        "/api/v1/production/branches/transfer",
        json={"from_branch_id": src, "to_branch_id": dst, "product_id": pid, "quantity": 10},
        headers=headers,
    )
    assert resp.status_code == 400, resp.text

    assert await _branch_qty(client_id, src, pid) == 3
    assert await _branch_qty(client_id, dst, pid) == 1
    async with db_manager.async_session_maker() as db:
        rows = (
            await db.execute(
                select(Stock_transfers).where(Stock_transfers.client_id == client_id)
            )
        ).scalars().all()
    assert rows == []
