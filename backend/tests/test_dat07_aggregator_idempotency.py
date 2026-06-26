"""DAT-07 — Aggregator ingest is idempotency-first / crash-safe.

The aggregator webhook (F-060) mints a **ZATCA-signed** invoice for each delivery
order. Before DAT-07 the ``channel_orders`` idempotency row was written *after* the
fiscal settle, with no DB constraint: a crash between minting the signed invoice and
recording the claim left no idempotency marker, so webhook re-delivery re-ran the
settle and minted a **second signed invoice** for the same order — a duplicate fiscal
document.

The fix claims the order **first** (insert ``status="received"`` and commit before any
fiscal work) and backs it with a unique ``(client_id, provider, external_order_id)``
constraint as the DB arbiter, so re-delivery after a partial failure mints **at most
one** invoice and a concurrent re-delivery can never double-book.
"""
import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from conftest import add_product, auth_headers, get_product_quantity, make_client_account
from core.database import db_manager
from models.channel_orders import Channel_orders
from models.clients import Clients
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


def _payload(*, location, order_id, qty=2, price=20.0):
    return {
        "location": location,
        "channelOrderId": order_id,
        "channelOrderDisplayId": "JZ-2001",
        "channel": "jahez",
        "orderType": "delivery",
        "customer": {"name": "Aggregator Customer", "phoneNumber": "+966500000000"},
        "items": [{"name": "Burger", "quantity": qty, "price": price}],
        "payment": {"amount": price * qty},
    }


async def _txn_count(client_id: int) -> int:
    async with db_manager.async_session_maker() as db:
        return (
            await db.execute(
                select(func.count(Transactions.id)).where(Transactions.client_id == client_id)
            )
        ).scalar() or 0


async def _doc_count(client_id: int) -> int:
    async with db_manager.async_session_maker() as db:
        return (
            await db.execute(
                select(func.count(ZatcaDocuments.id)).where(ZatcaDocuments.client_id == client_id)
            )
        ).scalar() or 0


@pytest.mark.asyncio
async def test_crash_after_settle_mints_at_most_one_invoice(client, monkeypatch):
    """A crash *after* the fiscal settle but *before* the order is recorded must not
    let re-delivery mint a second signed invoice — the claim is durable from the start.
    """
    user, token, client_id = await _restaurant_client(client)
    location = f"loc_{uuid.uuid4().hex[:8]}"
    await add_product(client_id, user["id"], name="Burger", quantity=10, price=20.0)
    async with db_manager.async_session_maker() as db:
        await db.execute(
            select(Clients).where(Clients.id == client_id)
        )  # warm
        row = (await db.execute(select(Clients).where(Clients.id == client_id))).scalar_one()
        row.aggregator_location_id = location
        await db.commit()

    payload = _payload(location=location, order_id="DLVR-CRASH-1")

    # First delivery: settle the invoice for real, then simulate a crash before the
    # ingest finishes recording the order as imported.
    from services.restaurant import RestaurantService

    original_settle = RestaurantService.settle_ticket

    async def settle_then_crash(self, *args, **kwargs):
        result = await original_settle(self, *args, **kwargs)
        raise RuntimeError("simulated crash after settle, before claim recorded")

    monkeypatch.setattr(RestaurantService, "settle_ticket", settle_then_crash)

    async with db_manager.async_session_maker() as db:
        clients_row = (await db.execute(select(Clients).where(Clients.id == client_id))).scalar_one()
        with pytest.raises(RuntimeError):
            await ingest_aggregator_order(db, clients_row, payload, "deliverect", 15.0)

    # The settle committed exactly one signed invoice.
    assert await _txn_count(client_id) == 1
    assert await _doc_count(client_id) == 1

    # Re-delivery (no crash this time) must NOT mint a second invoice.
    monkeypatch.setattr(RestaurantService, "settle_ticket", original_settle)
    async with db_manager.async_session_maker() as db:
        clients_row = (await db.execute(select(Clients).where(Clients.id == client_id))).scalar_one()
        again = await ingest_aggregator_order(db, clients_row, payload, "deliverect", 15.0)

    assert again["status"] == "duplicate"
    assert await _txn_count(client_id) == 1
    assert await _doc_count(client_id) == 1


@pytest.mark.asyncio
async def test_unique_constraint_rejects_duplicate_claim(client):
    """The DB is the arbiter: a second (client_id, provider, external_order_id) row
    is rejected, so a concurrent re-delivery racing past the SELECT can't double-book.
    """
    user, token, client_id = await _restaurant_client(client)
    eid = f"DLVR-{uuid.uuid4().hex[:8]}"

    async with db_manager.async_session_maker() as db:
        db.add(
            Channel_orders(
                user_id=user["id"],
                client_id=client_id,
                provider="deliverect",
                external_order_id=eid,
                status="received",
            )
        )
        await db.commit()

    with pytest.raises(IntegrityError):
        async with db_manager.async_session_maker() as db:
            db.add(
                Channel_orders(
                    user_id=user["id"],
                    client_id=client_id,
                    provider="deliverect",
                    external_order_id=eid,
                    status="received",
                )
            )
            await db.commit()
