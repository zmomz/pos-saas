"""issue #191 — first-touch branch-stock race must recover, not 500.

Two concurrent first sales of a product at a branch both see "no branch-stock
row" and both try to ``INSERT`` one. The loser violates ``uq_branch_stock`` and
gets an ``IntegrityError``. ``get_or_init_row`` must catch that, re-select the
row the winner committed, and return it — so the sale stays idempotent instead
of surfacing as a 500.

The race is made deterministic by forcing the *first* existence check to miss
(the stale read) while a committed row already exists in the DB — exactly the
state the losing transaction is in when it reaches the INSERT.
"""
from sqlalchemy import select

import services.branch_stock as bs
from conftest import add_product, make_client_account
from core.database import db_manager
from models.product_branch_stock import Product_branch_stock
from models.products import Products
from services.branch_stock import get_or_init_row, set_branch_stock

BRANCH_ID = 1


async def _load_product(db, client_id: int, product_id: int) -> Products:
    return (
        await db.execute(
            select(Products).where(
                Products.id == product_id, Products.client_id == client_id
            )
        )
    ).scalar_one()


async def test_first_touch_race_loser_reselects_existing_row(client, monkeypatch):
    user, token, client_id = await make_client_account(client)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=999, price=10.0)

    # The winner of the race has already committed the branch-stock row with 7 units.
    async with db_manager.async_session_maker() as db:
        await set_branch_stock(db, user["id"], client_id, BRANCH_ID, pid, 7)

    # Force the FIRST existence check to miss, reproducing the loser's stale read:
    # it sees no row, attempts an INSERT, and collides with the unique constraint.
    real_get_row = bs._get_row
    seen = {"n": 0}

    async def flaky_get_row(*a, **k):
        seen["n"] += 1
        if seen["n"] == 1:
            return None
        return await real_get_row(*a, **k)

    monkeypatch.setattr(bs, "_get_row", flaky_get_row)

    async with db_manager.async_session_maker() as db:
        product = await _load_product(db, client_id, pid)
        # Must NOT raise IntegrityError — it recovers by re-selecting the winner's row.
        row = await get_or_init_row(db, user["id"], client_id, BRANCH_ID, product)
        await db.commit()

    assert row is not None
    # It returned the existing committed row (7 units), not a duplicate fresh seed.
    assert row.quantity == 7

    # Exactly one row exists for the (client, branch, product) — no split rows.
    async with db_manager.async_session_maker() as db:
        rows = (
            await db.execute(
                select(Product_branch_stock).where(
                    Product_branch_stock.client_id == client_id,
                    Product_branch_stock.branch_id == BRANCH_ID,
                    Product_branch_stock.product_id == pid,
                )
            )
        ).scalars().all()
    assert len(rows) == 1
