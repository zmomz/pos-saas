"""DAT-05 — atomic invoice counter + unique (client_id, invoice_number) index.

Invoice/credit-note numbers must be minted with a single atomic
``UPDATE clients SET invoice_counter = invoice_counter + 1 RETURNING invoice_counter``
inside the sale transaction (not a read-modify-write on a possibly-stale ORM
value), so concurrent sales mint *distinct, sequential* fiscal numbers. A unique
index on ``(client_id, invoice_number)`` is the last-line backstop against a
duplicate fiscal document.
"""
import asyncio

import pytest
from sqlalchemy import select

from conftest import make_client_account
from core.database import db_manager
from models.clients import Clients
from models.transactions import Transactions
from services.invoice_counter import mint_invoice_number


async def _counter(client_id: int) -> int:
    async with db_manager.async_session_maker() as db:
        row = (
            await db.execute(select(Clients).where(Clients.id == client_id))
        ).scalar_one()
        return row.invoice_counter or 0


async def _mint(client_id: int, prefix: str = "INV") -> str:
    """Mint one number in its own short transaction (mirrors the sale txn)."""
    async with db_manager.async_session_maker() as db:
        number = await mint_invoice_number(db, client_id, prefix)
        await db.commit()
        return number


async def test_concurrent_mint_yields_distinct_sequential_numbers(client):
    """N=20 parallel mints on one client -> 20 distinct, contiguous numbers."""
    user, token, client_id = await make_client_account(client)
    start = await _counter(client_id)

    numbers = await asyncio.gather(*[_mint(client_id) for _ in range(20)])

    assert len(set(numbers)) == 20, f"duplicate fiscal numbers minted: {numbers}"
    counters = sorted(int(n.rsplit("-", 1)[1]) for n in numbers)
    assert counters == list(range(start + 1, start + 21))
    assert await _counter(client_id) == start + 20


async def test_credit_notes_share_the_same_atomic_counter(client):
    """A CRN refund draws from the same counter as INV sales, so a sale and a
    refund can never be minted with the same numeric suffix."""
    user, token, client_id = await make_client_account(client)

    inv1 = await _mint(client_id, "INV")
    crn = await _mint(client_id, "CRN")
    inv2 = await _mint(client_id, "INV")

    n1 = int(inv1.rsplit("-", 1)[1])
    nc = int(crn.rsplit("-", 1)[1])
    n2 = int(inv2.rsplit("-", 1)[1])
    assert crn.startswith("CRN-")
    assert (n1, nc, n2) == (n1, n1 + 1, n1 + 2)  # one shared monotonic sequence


async def test_unique_index_rejects_duplicate_invoice_number(client):
    """The (client_id, invoice_number) unique index is the last-line backstop: a
    second row with the same number for the same client must be rejected."""
    from sqlalchemy.exc import IntegrityError

    user, token, client_id = await make_client_account(client)
    dup = f"INV-{client_id:04d}-000999"

    async with db_manager.async_session_maker() as db:
        db.add(
            Transactions(
                user_id=user["id"], client_id=client_id, invoice_number=dup,
                total_amount=10.0, payment_method="cash", status="completed",
            )
        )
        await db.commit()

    async with db_manager.async_session_maker() as db:
        db.add(
            Transactions(
                user_id=user["id"], client_id=client_id, invoice_number=dup,
                total_amount=10.0, payment_method="cash", status="completed",
            )
        )
        with pytest.raises(IntegrityError):
            await db.commit()
