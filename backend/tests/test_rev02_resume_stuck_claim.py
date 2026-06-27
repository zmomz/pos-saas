"""REV-02 — Recover aggregator claims that were claimed but never settled.

DAT-07 made the aggregator ingest (F-060) claim the order (``status="received"``,
committed) BEFORE any fiscal work, so a crash mid-settle can never mint a second
signed invoice on webhook re-delivery. The gap REV-02 closes: if the process dies —
or ``execute_sale`` raises — **after** the claim commit but **before** any invoice is
minted, the claim is stranded at ``received`` with ``transaction_id IS NULL``. Under
DAT-07 a re-delivery saw the claim and returned ``duplicate``, so the transient
failure permanently dropped the sale (it was never invoiced).

The fix: a re-delivery of a stuck claim **resumes settlement** instead of refusing —
re-using the durable ticket so it never double-books — yet still mints **at most one**
invoice. The discriminator is the claimed ticket's status: a ticket already
``settled`` means an invoice exists (the DAT-07 crash-AFTER-settle case), so the
re-delivery must report ``duplicate`` and never mint a second; an unsettled ticket
means the settle never produced an invoice, so it is re-attempted.
"""
import uuid

import pytest
from sqlalchemy import func, select

from conftest import add_product, make_client_account
from core.database import db_manager
from models.channel_orders import Channel_orders
from models.clients import Clients
from models.restaurant import OrderTickets
from models.transactions import Transactions
from models.zatca_documents import ZatcaDocuments
from services.aggregator import ingest_aggregator_order


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
        "channelOrderDisplayId": "JZ-3001",
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


async def _claim(client_id: int) -> Channel_orders:
    async with db_manager.async_session_maker() as db:
        return (
            await db.execute(
                select(Channel_orders).where(Channel_orders.client_id == client_id)
            )
        ).scalar_one()


@pytest.mark.asyncio
async def test_resume_stuck_claim_settles_exactly_once(client, monkeypatch):
    """Claim committed + settle FAILS (no invoice) -> re-delivery completes the
    invoice exactly once and promotes the same claim to ``imported``.
    """
    user, token, client_id = await _restaurant_client(client)
    await add_product(client_id, user["id"], name="Burger", quantity=10, price=20.0)
    payload = _payload(order_id=f"DLVR-STUCK-{uuid.uuid4().hex[:8]}")

    from services.restaurant import RestaurantService

    original_settle = RestaurantService.settle_ticket

    async def settle_fail(self, *args, **kwargs):
        raise RuntimeError("simulated settle failure before any invoice is minted")

    monkeypatch.setattr(RestaurantService, "settle_ticket", settle_fail)

    # First delivery: claim commits, ticket is opened/fired, then the settle blows up
    # before any fiscal document is minted.
    async with db_manager.async_session_maker() as db:
        clients_row = (await db.execute(select(Clients).where(Clients.id == client_id))).scalar_one()
        with pytest.raises(RuntimeError):
            await ingest_aggregator_order(db, clients_row, payload, "deliverect", 15.0)

    assert await _count(Transactions, client_id) == 0  # nothing was invoiced
    assert await _count(ZatcaDocuments, client_id) == 0
    stuck = await _claim(client_id)
    assert stuck.status == "received"
    assert stuck.transaction_id is None
    assert stuck.ticket_id is not None  # the claim records its ticket for recovery

    # Re-delivery (no failure this time) must RESUME and mint the invoice once.
    monkeypatch.setattr(RestaurantService, "settle_ticket", original_settle)
    async with db_manager.async_session_maker() as db:
        clients_row = (await db.execute(select(Clients).where(Clients.id == client_id))).scalar_one()
        resumed = await ingest_aggregator_order(db, clients_row, payload, "deliverect", 15.0)

    assert resumed["status"] == "imported"
    assert resumed["transaction_id"] is not None
    assert await _count(Transactions, client_id) == 1
    assert await _count(ZatcaDocuments, client_id) == 1
    assert await _count(Channel_orders, client_id) == 1  # no second claim row
    assert await _count(OrderTickets, client_id) == 1  # reused the durable ticket

    done = await _claim(client_id)
    assert done.status == "imported"
    assert done.transaction_id == resumed["transaction_id"]


@pytest.mark.asyncio
async def test_resume_does_not_double_invoice_when_ticket_already_settled(client, monkeypatch):
    """Crash AFTER a successful settle (invoice minted) but before the claim is
    linked -> re-delivery must NOT mint a second invoice (DAT-07 no-regression),
    because the claimed ticket is already ``settled``.
    """
    user, token, client_id = await _restaurant_client(client)
    await add_product(client_id, user["id"], name="Burger", quantity=10, price=20.0)
    payload = _payload(order_id=f"DLVR-SETTLED-{uuid.uuid4().hex[:8]}")

    from services.restaurant import RestaurantService

    original_settle = RestaurantService.settle_ticket

    async def settle_then_crash(self, *args, **kwargs):
        result = await original_settle(self, *args, **kwargs)
        raise RuntimeError("crash after settle, before the claim is linked")

    monkeypatch.setattr(RestaurantService, "settle_ticket", settle_then_crash)

    async with db_manager.async_session_maker() as db:
        clients_row = (await db.execute(select(Clients).where(Clients.id == client_id))).scalar_one()
        with pytest.raises(RuntimeError):
            await ingest_aggregator_order(db, clients_row, payload, "deliverect", 15.0)

    assert await _count(Transactions, client_id) == 1  # exactly one invoice minted
    assert await _count(ZatcaDocuments, client_id) == 1

    # Re-delivery must detect the already-settled ticket and refuse to re-settle.
    monkeypatch.setattr(RestaurantService, "settle_ticket", original_settle)
    async with db_manager.async_session_maker() as db:
        clients_row = (await db.execute(select(Clients).where(Clients.id == client_id))).scalar_one()
        again = await ingest_aggregator_order(db, clients_row, payload, "deliverect", 15.0)

    assert again["status"] == "duplicate"
    assert await _count(Transactions, client_id) == 1  # still exactly one
    assert await _count(ZatcaDocuments, client_id) == 1
    assert await _count(OrderTickets, client_id) == 1  # no second ticket created
