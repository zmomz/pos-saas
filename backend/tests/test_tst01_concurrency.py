"""TST-01 — concurrency / atomicity coverage (audit F1).

The platform's correctness under concurrent load rests on a handful of
conditional-UPDATE / unique-constraint guarantees that the DAT-0x slices put in
place. Those slices each ship their own focused test; this module is the
consolidated *concurrent-load* suite the audit called for — one ``asyncio.gather``
race per invariant, asserting the guarantee holds when N callers hit the same row
at once:

* N parallel one-unit sales on stock=K  -> exactly K succeed, no oversell.
* N parallel invoice mints on one client -> N distinct, contiguous numbers.
* N parallel client provisions on a package of K slots -> exactly K succeed.
* N parallel syncs of one offline_id     -> exactly one sale is booked.

Each test fails on the pre-fix (read-check-write) code and passes on the atomic
version, so the suite is a regression backstop against anyone reintroducing a
race.
"""
import asyncio

from fastapi import HTTPException
from sqlalchemy import func, select
from types import SimpleNamespace

from conftest import (
    add_product,
    auth_headers,
    get_product_quantity,
    make_agent_account,
    make_client_account,
    unique_email,
)
from core.database import db_manager


# --------------------------------------------------------------------------- #
# Slot allocation: a package of K slots must let exactly K concurrent client
# provisions through, even when N > K agents race for the last slot (MA-02).
# --------------------------------------------------------------------------- #
async def test_concurrent_client_provisioning_respects_package_capacity(client):
    """package_type=3, 10 parallel POST /agent/clients -> exactly 3 succeed (200),
    the other 7 get 409 'no available slots', and used_slots lands on exactly 3."""
    capacity = 3
    attempts = 10
    user, token, agent_id = await make_agent_account(client, package_type=capacity)

    async def provision() -> int:
        resp = await client.post(
            "/api/v1/tenant/agent/clients",
            headers=auth_headers(token),
            json={"business_name": "Shop", "email": unique_email()},
        )
        return resp.status_code

    codes = await asyncio.gather(*[provision() for _ in range(attempts)])

    assert sum(c == 200 for c in codes) == capacity, codes
    assert sum(c == 409 for c in codes) == attempts - capacity, codes

    from models.agents import Agents

    async with db_manager.async_session_maker() as db:
        agent = (
            await db.execute(select(Agents).where(Agents.id == agent_id))
        ).scalar_one()
        assert agent.used_slots == capacity


# --------------------------------------------------------------------------- #
# Stock: N parallel one-unit sales on stock=K must let exactly K through, with
# no oversell, via the conditional `... WHERE quantity >= :q` decrement (DAT-01).
# --------------------------------------------------------------------------- #
async def test_concurrent_sales_never_oversell_stock(client):
    """K=4 units, 16 parallel one-unit deductions -> exactly 4 sell, stock = 0."""
    from services.sale_core import deduct_inventory

    capacity = 4
    attempts = 16
    user, token, client_id = await make_client_account(client)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=capacity)

    async def sell_one() -> bool:
        async with db_manager.async_session_maker() as db:
            try:
                await deduct_inventory(
                    db, client_id, [SimpleNamespace(product_id=pid, quantity=1)], False
                )
                await db.commit()
                return True
            except HTTPException:
                await db.rollback()
                return False

    results = await asyncio.gather(*[sell_one() for _ in range(attempts)])

    assert sum(results) == capacity, results
    assert await get_product_quantity(pid) == 0


# --------------------------------------------------------------------------- #
# Invoice counter: N parallel mints on one client must yield N distinct,
# contiguous fiscal numbers (atomic UPDATE ... RETURNING, DAT-05).
# --------------------------------------------------------------------------- #
async def test_concurrent_invoice_mints_are_distinct_and_contiguous(client):
    """15 parallel mints on one client -> 15 unique, gap-free sequential numbers."""
    from services.invoice_counter import mint_invoice_number

    attempts = 15
    user, token, client_id = await make_client_account(client)

    async def mint() -> str:
        async with db_manager.async_session_maker() as db:
            number = await mint_invoice_number(db, client_id, "INV")
            await db.commit()
            return number

    numbers = await asyncio.gather(*[mint() for _ in range(attempts)])

    assert len(set(numbers)) == attempts, f"duplicate fiscal numbers: {numbers}"
    suffixes = sorted(int(n.rsplit("-", 1)[1]) for n in numbers)
    assert suffixes == list(range(1, attempts + 1))


# --------------------------------------------------------------------------- #
# Offline idempotency: N parallel syncs of one offline_id must book exactly one
# sale — the unique (client_id, offline_id) constraint is the arbiter (DAT-06).
# --------------------------------------------------------------------------- #
async def test_concurrent_offline_resync_books_single_sale(client):
    """Five parallel syncs of the same offline_id -> exactly one transaction row,
    and the batch reports a single processed sale across all responses."""
    from models.transactions import Transactions

    user, token, client_id = await make_client_account(client)
    oid = "OFFLINE-RACE-TST01"
    payload = {
        "transactions": [
            {
                "offline_id": oid,
                "client_id": client_id,
                "subtotal": 50.0,
                "vat_amount": 7.5,
                "total_amount": 57.5,
                "payment_method": "cash",
                "items": [{"product_id": 1, "name": "W", "price": 50, "quantity": 1}],
            }
        ]
    }

    async def sync() -> dict:
        resp = await client.post(
            "/api/v1/production/offline/sync",
            headers=auth_headers(token),
            json=payload,
        )
        assert resp.status_code == 200, resp.text
        return resp.json()

    batches = await asyncio.gather(*[sync() for _ in range(5)])

    # Across every racing sync, exactly one booked the sale; the rest skipped it.
    assert sum(b["processed"] for b in batches) == 1, batches
    assert sum(b["skipped_duplicates"] for b in batches) == 4, batches

    async with db_manager.async_session_maker() as db:
        count = (
            await db.execute(
                select(func.count(Transactions.id)).where(
                    Transactions.client_id == client_id,
                    Transactions.offline_id == oid,
                )
            )
        ).scalar_one()
    assert count == 1
