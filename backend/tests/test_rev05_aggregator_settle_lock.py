"""REV-05 — the aggregator resume path must be mutually exclusive (#179).

REV-02 (#175) let a re-delivery *resume* a claim still at ``received`` with no
transaction by re-running settlement — with NO mutual exclusion. The aggregator
middleware re-delivers (sometimes concurrently), so two deliveries reading the same
unsettled claim both opened a ticket, fired the KDS, and settled — minting **two**
signed ZATCA invoices, **two** KDS tickets, and a double stock decrement for one
order.

The fix: the settler must win an atomic ``received -> settling`` compare-and-set
before any fiscal work. Exactly one caller (fresh or resume) ever wins it for a given
claim attempt, so a concurrent re-delivery backs off as a duplicate. A claim whose
settler crashed mid-flight is stranded at ``settling`` and recovered only by the
bounded sweep (never by a concurrent caller resuming on sight).
"""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from conftest import add_product, make_client_account
from core.database import db_manager
from models.channel_orders import Channel_orders
from models.clients import Clients
from models.restaurant import OrderTickets
from models.transactions import Transactions
from models.zatca_documents import ZatcaDocuments
from services.aggregator import ingest_aggregator_order, recover_stuck_aggregator_claims


async def _set_vat(client_id: int, vat: str = "300000000000003"):
    async with db_manager.async_session_maker() as db:
        row = (await db.execute(select(Clients).where(Clients.id == client_id))).scalar_one()
        row.vat_number = vat
        await db.commit()


async def _restaurant_client(client):
    user, token, client_id = await make_client_account(client, business_type="restaurant")
    await _set_vat(client_id)
    return user, token, client_id


def _payload(*, order_id, qty=2, price=20.0):
    return {
        "channelOrderId": order_id,
        "channelOrderDisplayId": "JZ-5001",
        "channel": "jahez",
        "orderType": "delivery",
        "customer": {"name": "Aggregator Customer", "phoneNumber": "+966500000000"},
        "items": [{"name": "Burger", "quantity": qty, "price": price}],
        "payment": {"amount": price * qty},
    }


async def _count(model, client_id: int) -> int:
    async with db_manager.async_session_maker() as db:
        return (
            await db.execute(
                select(func.count(model.id)).where(model.client_id == client_id)
            )
        ).scalar() or 0


async def _seed_stuck_claim(user_id, client_id, external_id, *, ticket_id=None, status="received"):
    """Insert a claim stranded after the DAT-07 claim-commit but before settle."""
    async with db_manager.async_session_maker() as db:
        db.add(
            Channel_orders(
                user_id=user_id,
                client_id=client_id,
                provider="deliverect",
                external_order_id=external_id,
                transaction_id=None,
                ticket_id=ticket_id,
                status=status,
                total_amount=40.0,
                currency="SAR",
            )
        )
        await db.commit()


async def _claim(client_id: int) -> Channel_orders:
    async with db_manager.async_session_maker() as db:
        return (
            await db.execute(
                select(Channel_orders).where(Channel_orders.client_id == client_id)
            )
        ).scalar_one()


@pytest.mark.asyncio
async def test_concurrent_redelivery_settles_exactly_once(client):
    """Two concurrent re-deliveries of one stuck claim mint exactly one invoice and
    one ticket — the loser backs off as a duplicate."""
    user, token, client_id = await _restaurant_client(client)
    await add_product(client_id, user["id"], name="Burger", quantity=10, price=20.0)
    external_id = f"DLVR-RACE-{uuid.uuid4().hex[:8]}"
    await _seed_stuck_claim(user["id"], client_id, external_id)

    payload = _payload(order_id=external_id)

    async def deliver():
        async with db_manager.async_session_maker() as db:
            clients_row = (
                await db.execute(select(Clients).where(Clients.id == client_id))
            ).scalar_one()
            return await ingest_aggregator_order(db, clients_row, payload, "deliverect", 15.0)

    results = await asyncio.gather(deliver(), deliver(), return_exceptions=True)

    # No call may raise.
    raised = [r for r in results if isinstance(r, Exception)]
    assert not raised, f"a delivery raised: {raised}"

    statuses = sorted(r["status"] for r in results)
    assert statuses == ["duplicate", "imported"], statuses

    assert await _count(Transactions, client_id) == 1  # exactly one signed invoice
    assert await _count(ZatcaDocuments, client_id) == 1
    assert await _count(OrderTickets, client_id) == 1  # exactly one KDS ticket
    assert await _count(Channel_orders, client_id) == 1

    done = await _claim(client_id)
    assert done.status == "imported"
    assert done.transaction_id is not None


@pytest.mark.asyncio
async def test_bounded_sweep_reopens_crashed_settling_claim(client):
    """A claim stranded in ``settling`` (settler crashed mid-flight) is re-opened by
    the bounded sweep once it is older than the threshold — then a re-delivery settles
    it exactly once. A freshly-locked claim is left alone."""
    user, token, client_id = await _restaurant_client(client)
    await add_product(client_id, user["id"], name="Burger", quantity=10, price=20.0)
    external_id = f"DLVR-CRASH-{uuid.uuid4().hex[:8]}"
    await _seed_stuck_claim(user["id"], client_id, external_id, status="settling")

    # Stamp the lock far in the past so it is "stuck".
    async with db_manager.async_session_maker() as db:
        row = (
            await db.execute(select(Channel_orders).where(Channel_orders.client_id == client_id))
        ).scalar_one()
        row.settling_at = datetime.now(timezone.utc) - timedelta(minutes=30)
        await db.commit()

    # A fresh lock (just now) must NOT be re-opened by the sweep.
    async with db_manager.async_session_maker() as db:
        reopened = await recover_stuck_aggregator_claims(db, threshold_seconds=600)
    assert reopened == 1
    after = await _claim(client_id)
    assert after.status == "received"
    assert after.settling_at is None

    # Now a re-delivery resumes and settles exactly once.
    payload = _payload(order_id=external_id)
    async with db_manager.async_session_maker() as db:
        clients_row = (
            await db.execute(select(Clients).where(Clients.id == client_id))
        ).scalar_one()
        resumed = await ingest_aggregator_order(db, clients_row, payload, "deliverect", 15.0)

    assert resumed["status"] == "imported"
    assert await _count(Transactions, client_id) == 1
    assert await _count(ZatcaDocuments, client_id) == 1


@pytest.mark.asyncio
async def test_sweep_leaves_fresh_lock_alone(client):
    """A claim locked just now is an in-flight settle, not a crash — the sweep skips it."""
    user, token, client_id = await _restaurant_client(client)
    external_id = f"DLVR-FRESH-{uuid.uuid4().hex[:8]}"
    await _seed_stuck_claim(user["id"], client_id, external_id, status="settling")
    async with db_manager.async_session_maker() as db:
        row = (
            await db.execute(select(Channel_orders).where(Channel_orders.client_id == client_id))
        ).scalar_one()
        row.settling_at = datetime.now(timezone.utc)
        await db.commit()

    async with db_manager.async_session_maker() as db:
        reopened = await recover_stuck_aggregator_claims(db, threshold_seconds=600)
    assert reopened == 0
    after = await _claim(client_id)
    assert after.status == "settling"
