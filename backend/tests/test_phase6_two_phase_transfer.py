"""ISSUE-061 — two-phase inter-branch stock transfer (dispatch → receive).

The one-step transfer (F-032) moves stock instantly. A two-phase transfer models
a real shipment: stock leaves the source on **dispatch** (in-transit), and lands at
the destination only on **receive**. A discrepancy between the quantity dispatched
and the quantity actually received is recorded on the transfer.

These tests pin the corrected behavior:

- dispatch decrements the source ledger by N, marks the transfer ``in_transit`` and
  does NOT touch the destination;
- receive increments the destination ledger and closes the transfer (``received``);
- a short receive records the discrepancy (dispatched − received);
- both endpoints are owner-scoped (SEC-02).
"""
import pytest
from sqlalchemy import select

from conftest import add_product, auth_headers, make_client_account
from core.database import db_manager
from models.stock_transfers import Stock_transfers


async def _make_branch(client, headers, name):
    resp = await client.post(
        "/api/v1/entities/branches",
        json={"name": name, "is_active": True},
        headers=headers,
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


async def _branch_qty(client, headers, branch_id, product_id):
    resp = await client.get(f"/api/v1/pos/branches/{branch_id}/stock", headers=headers)
    return {i["product_id"]: i["quantity"] for i in resp.json()["items"]}.get(product_id)


@pytest.mark.asyncio
async def test_dispatch_decrements_source_and_marks_in_transit(client):
    """Dispatch N units → source−N, transfer ``in_transit``, destination untouched."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=0, price=10.0)
    src = await _make_branch(client, headers, "Main")
    dst = await _make_branch(client, headers, "Second")
    await _allocate(client, headers, src, pid, 50)
    await _allocate(client, headers, dst, pid, 20)

    resp = await client.post(
        "/api/v1/production/branches/transfer/dispatch",
        json={"from_branch_id": src, "to_branch_id": dst, "product_id": pid, "quantity": 10},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "in_transit"
    assert body["from_branch_quantity"] == 40

    # Source lost the stock; destination is unchanged until receive.
    assert await _branch_qty(client, headers, src, pid) == 40
    assert await _branch_qty(client, headers, dst, pid) == 20

    async with db_manager.async_session_maker() as db:
        rows = (
            await db.execute(
                select(Stock_transfers).where(Stock_transfers.client_id == client_id)
            )
        ).scalars().all()
    assert len(rows) == 1
    assert rows[0].status == "in_transit"
    assert rows[0].quantity == 10


@pytest.mark.asyncio
async def test_receive_credits_destination_and_closes_transfer(client):
    """Full cycle: receive an in-transit transfer → dest+N, status ``received``."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=0, price=10.0)
    src = await _make_branch(client, headers, "Main")
    dst = await _make_branch(client, headers, "Second")
    await _allocate(client, headers, src, pid, 50)
    await _allocate(client, headers, dst, pid, 20)

    dispatch = await client.post(
        "/api/v1/production/branches/transfer/dispatch",
        json={"from_branch_id": src, "to_branch_id": dst, "product_id": pid, "quantity": 10},
        headers=headers,
    )
    transfer_id = dispatch.json()["id"]

    resp = await client.post(
        f"/api/v1/production/branches/transfer/{transfer_id}/receive",
        json={},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "received"
    assert body["received_quantity"] == 10
    assert body["discrepancy"] == 0
    assert body["to_branch_quantity"] == 30

    # Destination now credited; source stayed down. No double-credit.
    assert await _branch_qty(client, headers, src, pid) == 40
    assert await _branch_qty(client, headers, dst, pid) == 30

    async with db_manager.async_session_maker() as db:
        row = (
            await db.execute(
                select(Stock_transfers).where(Stock_transfers.id == transfer_id)
            )
        ).scalar_one()
    assert row.status == "received"
    assert row.received_quantity == 10


@pytest.mark.asyncio
async def test_receive_rejects_non_in_transit_transfer(client):
    """A transfer can only be received once; a second receive is a 400."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=0, price=10.0)
    src = await _make_branch(client, headers, "Main")
    dst = await _make_branch(client, headers, "Second")
    await _allocate(client, headers, src, pid, 50)

    transfer_id = (
        await client.post(
            "/api/v1/production/branches/transfer/dispatch",
            json={"from_branch_id": src, "to_branch_id": dst, "product_id": pid, "quantity": 10},
            headers=headers,
        )
    ).json()["id"]
    first = await client.post(
        f"/api/v1/production/branches/transfer/{transfer_id}/receive",
        json={},
        headers=headers,
    )
    assert first.status_code == 200, first.text

    second = await client.post(
        f"/api/v1/production/branches/transfer/{transfer_id}/receive",
        json={},
        headers=headers,
    )
    assert second.status_code == 400, second.text
    # The destination was not credited a second time.
    assert await _branch_qty(client, headers, dst, pid) == 10


@pytest.mark.asyncio
async def test_short_receive_records_discrepancy(client):
    """Receiving fewer units than dispatched records the shortfall and credits
    only what arrived (in-transit shrink)."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=0, price=10.0)
    src = await _make_branch(client, headers, "Main")
    dst = await _make_branch(client, headers, "Second")
    await _allocate(client, headers, src, pid, 50)
    await _allocate(client, headers, dst, pid, 0)

    transfer_id = (
        await client.post(
            "/api/v1/production/branches/transfer/dispatch",
            json={"from_branch_id": src, "to_branch_id": dst, "product_id": pid, "quantity": 10},
            headers=headers,
        )
    ).json()["id"]

    resp = await client.post(
        f"/api/v1/production/branches/transfer/{transfer_id}/receive",
        json={"received_quantity": 8},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["received_quantity"] == 8
    assert body["discrepancy"] == 2  # dispatched 10 − received 8
    assert body["to_branch_quantity"] == 8  # only what arrived

    async with db_manager.async_session_maker() as db:
        row = (
            await db.execute(
                select(Stock_transfers).where(Stock_transfers.id == transfer_id)
            )
        ).scalar_one()
    assert row.received_quantity == 8
    assert row.discrepancy == 2


@pytest.mark.asyncio
async def test_receive_is_owner_scoped(client):
    """A client cannot receive another client's in-transit transfer (SEC-02)."""
    user_a, token_a, client_id_a = await make_client_account(client)
    headers_a = auth_headers(token_a)
    pid_a = await add_product(client_id_a, user_a["id"], quantity=0, price=10.0)
    src_a = await _make_branch(client, headers_a, "A-Main")
    dst_a = await _make_branch(client, headers_a, "A-Second")
    await _allocate(client, headers_a, src_a, pid_a, 30)
    transfer_id = (
        await client.post(
            "/api/v1/production/branches/transfer/dispatch",
            json={"from_branch_id": src_a, "to_branch_id": dst_a, "product_id": pid_a, "quantity": 5},
            headers=headers_a,
        )
    ).json()["id"]

    _user_b, token_b, _ = await make_client_account(client)
    headers_b = auth_headers(token_b)
    resp = await client.post(
        f"/api/v1/production/branches/transfer/{transfer_id}/receive",
        json={},
        headers=headers_b,
    )
    assert resp.status_code == 404, resp.text
