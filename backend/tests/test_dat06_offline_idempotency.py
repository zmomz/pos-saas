"""DAT-06 — unique (client_id, offline_id) + insert-conflict idempotency.

Offline-queued sales carry a client-generated ``offline_id``. The sync path
deduplicates on it so re-syncing the same queue (a flaky connection that retries,
two tabs flushing at once) never double-books a sale. Before DAT-06 the dedup was
a SELECT-then-insert with no DB constraint, so two concurrent syncs of the same
``offline_id`` both saw "not present" and both inserted -> a double-booked sale.

The fix: a unique ``(client_id, offline_id)`` constraint makes the database the
arbiter, and the sync path treats an insert-conflict as the idempotency signal —
rolling back and returning the *already-persisted* transaction instead of a
second one. NULL ``offline_id`` rows (live sales, held tickets, credit notes) are
exempt: NULLs are distinct, so they never collide.
"""
import asyncio

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from conftest import auth_headers, make_client_account
from core.database import db_manager
from models.transactions import Transactions


def _queued(client_id: int, offline_id: str) -> dict:
    return {
        "transactions": [
            {
                "offline_id": offline_id,
                "client_id": client_id,
                "subtotal": 50.0,
                "vat_amount": 7.5,
                "total_amount": 57.5,
                "payment_method": "cash",
                "items": [{"product_id": 1, "name": "W", "price": 50, "quantity": 1}],
            }
        ]
    }


async def _count_offline(client_id: int, offline_id: str) -> int:
    async with db_manager.async_session_maker() as db:
        return (
            await db.execute(
                select(func.count(Transactions.id)).where(
                    Transactions.client_id == client_id,
                    Transactions.offline_id == offline_id,
                )
            )
        ).scalar_one()


async def test_unique_constraint_rejects_duplicate_offline_id(client):
    """A second raw insert with the same (client_id, offline_id) is rejected."""
    user, token, client_id = await make_client_account(client)
    oid = "offline-abc-123"

    async with db_manager.async_session_maker() as db:
        db.add(
            Transactions(
                user_id=user["id"], client_id=client_id, offline_id=oid,
                invoice_number=f"INV-{client_id:04d}-100001",
                total_amount=10.0, payment_method="cash", status="completed",
            )
        )
        await db.commit()

    async with db_manager.async_session_maker() as db:
        db.add(
            Transactions(
                user_id=user["id"], client_id=client_id, offline_id=oid,
                invoice_number=f"INV-{client_id:04d}-100002",
                total_amount=10.0, payment_method="cash", status="completed",
            )
        )
        with pytest.raises(IntegrityError):
            await db.commit()


async def test_sequential_resync_returns_existing_transaction(client):
    """Re-syncing the same offline_id books one sale; the second sync skips and
    echoes the *already-persisted* transaction (id + invoice_number), and the
    batch reports the offline_id as accepted (settled) — what FE-03 deletes on."""
    user, token, client_id = await make_client_account(client)
    oid = "OFFLINE-SEQ-1"

    first = await client.post(
        "/api/v1/production/offline/sync",
        headers=auth_headers(token),
        json=_queued(client_id, oid),
    )
    assert first.status_code == 200, first.text
    fb = first.json()
    assert fb["processed"] == 1 and fb["skipped_duplicates"] == 0
    booked = fb["results"][0]
    assert booked["offline_id"] == oid
    assert booked["transaction_id"] is not None
    assert oid in fb["accepted_offline_ids"]

    second = await client.post(
        "/api/v1/production/offline/sync",
        headers=auth_headers(token),
        json=_queued(client_id, oid),
    )
    assert second.status_code == 200, second.text
    sb = second.json()
    assert sb["processed"] == 0 and sb["skipped_duplicates"] == 1
    # A skip is idempotent, not a black hole: it returns the original sale so the
    # caller can reconcile, and the offline_id is still "accepted" (safe to drop).
    skipped = sb["results"][0]
    assert skipped["status"] == "skipped"
    assert skipped["offline_id"] == oid
    assert skipped["transaction_id"] == booked["transaction_id"]
    assert skipped["invoice_number"] == booked["invoice_number"]
    assert oid in sb["accepted_offline_ids"]

    assert await _count_offline(client_id, oid) == 1


async def test_concurrent_resync_books_single_sale(client, monkeypatch):
    """Two syncs of the same offline_id racing through the pre-check (both see
    "not present") must still book exactly ONE sale: the unique constraint makes
    the loser's insert conflict, and the sync path treats that conflict as the
    idempotency signal — rolling back and returning the winner's transaction."""
    import routers.pos as pos

    user, token, client_id = await make_client_account(client)
    oid = "OFFLINE-RACE-1"

    real_mint = pos.mint_invoice_number
    gate = asyncio.Event()
    arrived = 0
    lock = asyncio.Lock()

    async def gated_mint(db, cid, prefix):
        # Hold every racer here until both have cleared the pre-check, so the
        # second insert is guaranteed to hit a committed duplicate (the real race).
        nonlocal arrived
        async with lock:
            arrived += 1
            if arrived >= 2:
                gate.set()
        await gate.wait()
        return await real_mint(db, cid, prefix)

    monkeypatch.setattr(pos, "mint_invoice_number", gated_mint)

    async def one():
        async with db_manager.async_session_maker() as db:
            return await pos.process_offline_sale(
                db, user["id"], client_id,
                {
                    "offline_id": oid, "client_id": client_id,
                    "payment_method": "cash",
                    "items": [{"product_id": 1, "name": "W", "price": 50, "quantity": 1}],
                },
            )

    outcomes = await asyncio.gather(one(), one())

    # Exactly one sale row exists for the offline_id.
    assert await _count_offline(client_id, oid) == 1
    # Both calls succeeded (no leaked IntegrityError) and agree on the same sale.
    ids = {o["transaction_id"] for o in outcomes}
    assert len(ids) == 1 and None not in ids
    statuses = sorted(o["status"] for o in outcomes)
    assert statuses == ["processed", "skipped"]
