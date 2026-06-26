"""DAT-08 — Guard empty/zero-line aggregator orders before settle.

Before DAT-08 the aggregator ingest (F-060) unconditionally opened a tableless
ticket, fired its courses to the KDS, and drove a ZATCA settle — even when the
order carried **no billable lines** (every item missing or with quantity <= 0).
That left an orphan ``order_ticket`` + KDS card behind and tried to settle a
zero-line check; a webhook re-delivery then 500'd on the dangling state.

The fix mirrors Salla's graceful behaviour (services/omnichannel.py): the order
is still claimed for idempotency, but with **zero** billable lines no ticket /
KDS card is created and no settle runs — the ingest returns a ``no_lines``
status and leaves the claim row at ``received`` (no transaction).
"""
import uuid

import pytest
from sqlalchemy import func, select

from conftest import add_product, make_client_account
from core.database import db_manager
from models.channel_orders import Channel_orders
from models.clients import Clients
from models.restaurant import KdsTickets, OrderTickets
from models.transactions import Transactions
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


def _payload(*, order_id, items):
    return {
        "channelOrderId": order_id,
        "channelOrderDisplayId": "JZ-9001",
        "channel": "jahez",
        "orderType": "delivery",
        "customer": {"name": "Empty Order Customer", "phoneNumber": "+966500000000"},
        "items": items,
        "payment": {"amount": 0.0},
    }


async def _count(model, client_id: int) -> int:
    async with db_manager.async_session_maker() as db:
        return (
            await db.execute(
                select(func.count(model.id)).where(model.client_id == client_id)
            )
        ).scalar() or 0


@pytest.mark.asyncio
async def test_empty_order_returns_no_lines_without_ticket_or_settle(client):
    """An order with no billable lines mints no ticket/KDS/transaction and reports
    ``no_lines`` — but is still claimed (idempotency marker recorded)."""
    user, token, client_id = await _restaurant_client(client)
    # Every item is non-billable: one with qty 0, one a non-dict.
    payload = _payload(
        order_id=f"DLVR-EMPTY-{uuid.uuid4().hex[:8]}",
        items=[{"name": "Burger", "quantity": 0, "price": 20.0}, "garbage"],
    )

    async with db_manager.async_session_maker() as db:
        clients_row = (await db.execute(select(Clients).where(Clients.id == client_id))).scalar_one()
        result = await ingest_aggregator_order(db, clients_row, payload, "deliverect", 15.0)

    assert result["status"] == "no_lines"
    assert result["transaction_id"] is None
    assert result["matched_lines"] == 0

    # No fiscal side effects, no orphan ticket / KDS card.
    assert await _count(Transactions, client_id) == 0
    assert await _count(OrderTickets, client_id) == 0
    assert await _count(KdsTickets, client_id) == 0

    # The claim row IS recorded (so re-delivery dedupes) but stays at ``received``.
    async with db_manager.async_session_maker() as db:
        claim = (
            await db.execute(
                select(Channel_orders).where(Channel_orders.client_id == client_id)
            )
        ).scalar_one()
        assert claim.status == "received"
        assert claim.transaction_id is None


@pytest.mark.asyncio
async def test_nonempty_order_still_imports(client):
    """A normal order with a billable line is unaffected: it imports, opening a
    ticket and minting a transaction."""
    user, token, client_id = await _restaurant_client(client)
    await add_product(client_id, user["id"], name="Burger", quantity=10, price=20.0)
    payload = _payload(
        order_id=f"DLVR-OK-{uuid.uuid4().hex[:8]}",
        items=[{"name": "Burger", "quantity": 2, "price": 20.0}],
    )

    async with db_manager.async_session_maker() as db:
        clients_row = (await db.execute(select(Clients).where(Clients.id == client_id))).scalar_one()
        result = await ingest_aggregator_order(db, clients_row, payload, "deliverect", 15.0)

    assert result["status"] == "imported"
    assert result["transaction_id"] is not None
    assert await _count(Transactions, client_id) == 1
    assert await _count(OrderTickets, client_id) == 1
