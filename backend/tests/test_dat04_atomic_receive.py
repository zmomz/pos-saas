"""DAT-04 (receive leg) — atomic two-phase transfer *receive*.

DAT-04 (#126) made the **dispatch** leg of an inter-branch transfer a single
conditional decrement, but the **receive** leg in ``receive_branch_stock`` was
still read-check-write: it checked ``status == "in_transit"`` then credited the
destination and flipped the row via the ORM. Two concurrent receives (a
double-click, two managers) both read ``in_transit``, both pass the guard, and
both credit the destination → stock created from nothing.

``receive_branch_inventory`` must close the transfer with a single conditional
UPDATE (``... SET status='received' WHERE id=:id AND status='in_transit'``) and
credit the destination with one atomic increment *only* when that gate wins
(rowcount == 1). So N concurrent receives of one in-transit transfer credit the
destination **exactly once** and the transfer settles once.
"""
import asyncio

import pytest
from sqlalchemy import select

from conftest import add_product, auth_headers, make_client_account
from core.database import db_manager
from models.product_branch_stock import Product_branch_stock
from models.products import Products
from models.stock_transfers import Stock_transfers
from services.branch_stock import receive_branch_inventory, set_branch_stock

SRC_BRANCH = 1
DST_BRANCH = 2


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


async def _seed(user_id, client_id, branch_id, product_id, qty):
    async with db_manager.async_session_maker() as db:
        await set_branch_stock(db, user_id, client_id, branch_id, product_id, qty)


async def _make_in_transit(user_id, client_id, product_id, qty) -> int:
    """Write an ``in_transit`` transfer row directly and return its id."""
    async with db_manager.async_session_maker() as db:
        record = Stock_transfers(
            user_id=str(user_id),
            client_id=client_id,
            from_branch_id=SRC_BRANCH,
            to_branch_id=DST_BRANCH,
            product_id=product_id,
            product_name="Cola",
            quantity=qty,
            status="in_transit",
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)
        return record.id


async def _receive_one(user_id, client_id, transfer_id, received) -> bool:
    """Run a single receive in its own transaction; True if this caller won."""
    async with db_manager.async_session_maker() as db:
        transfer = (
            await db.execute(
                select(Stock_transfers).where(Stock_transfers.id == transfer_id)
            )
        ).scalar_one()
        product = (
            await db.execute(select(Products).where(Products.id == transfer.product_id))
        ).scalar_one()
        won, _dst_qty = await receive_branch_inventory(
            db, user_id, client_id, transfer, product, received
        )
        await db.commit()
        return won


@pytest.mark.asyncio
async def test_concurrent_receives_credit_destination_exactly_once(client):
    """N=20 parallel receives of one in-transit transfer of 10 units → exactly one
    wins, the destination is credited 10 (not 10*winners), and stock is conserved."""
    user, _token, client_id = await make_client_account(client)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=999, price=10.0)
    await _seed(user["id"], client_id, SRC_BRANCH, pid, 40)  # source already shed 10
    await _seed(user["id"], client_id, DST_BRANCH, pid, 20)
    transfer_id = await _make_in_transit(user["id"], client_id, pid, 10)

    results = await asyncio.gather(
        *[_receive_one(user["id"], client_id, transfer_id, 10) for _ in range(20)]
    )

    assert sum(results) == 1  # exactly one receive settled the transfer
    assert await _branch_qty(client_id, DST_BRANCH, pid) == 30  # 20 + 10, credited once
    assert await _branch_qty(client_id, SRC_BRANCH, pid) == 40  # untouched on receive

    async with db_manager.async_session_maker() as db:
        row = (
            await db.execute(
                select(Stock_transfers).where(Stock_transfers.id == transfer_id)
            )
        ).scalar_one()
    assert row.status == "received"
    assert row.received_quantity == 10
