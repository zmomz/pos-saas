"""F-032 — inter-branch stock transfers (INV-05).

The Branch Management "Transfer Stock" dialog POSTed to
``/api/v1/production/branches/transfer`` — a route that did not exist, so the action
404'd (a dead-end UI). These tests pin the corrected behavior:

- a transfer of N units decrements the source branch ledger by N and increments the
  destination by N, and writes a ``stock_transfers`` audit row;
- insufficient source stock is rejected (400) and nothing moves;
- the endpoint is owner-scoped — a client cannot transfer using another client's
  branches (SEC-02).
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


@pytest.mark.asyncio
async def test_transfer_moves_stock_and_records(client):
    """Transfer N units → source−N / dest+N on the ledger + a transfer record."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=0, price=10.0)
    src = await _make_branch(client, headers, "Main")
    dst = await _make_branch(client, headers, "Second")
    await _allocate(client, headers, src, pid, 50)
    await _allocate(client, headers, dst, pid, 20)

    resp = await client.post(
        "/api/v1/production/branches/transfer",
        json={"from_branch_id": src, "to_branch_id": dst, "product_id": pid, "quantity": 10},
        headers=headers,
    )
    # The route exists (no longer a 404 dead-end) and the move succeeds.
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "received"
    assert body["from_branch_quantity"] == 40
    assert body["to_branch_quantity"] == 30

    # Ledger reflects the move on both branches.
    src_stock = await client.get(f"/api/v1/pos/branches/{src}/stock", headers=headers)
    dst_stock = await client.get(f"/api/v1/pos/branches/{dst}/stock", headers=headers)
    assert {i["product_id"]: i["quantity"] for i in src_stock.json()["items"]}[pid] == 40
    assert {i["product_id"]: i["quantity"] for i in dst_stock.json()["items"]}[pid] == 30

    # An audit row was written.
    async with db_manager.async_session_maker() as db:
        rows = (
            await db.execute(
                select(Stock_transfers).where(Stock_transfers.client_id == client_id)
            )
        ).scalars().all()
    assert len(rows) == 1
    assert rows[0].from_branch_id == src and rows[0].to_branch_id == dst
    assert rows[0].product_id == pid and rows[0].quantity == 10


@pytest.mark.asyncio
async def test_transfer_insufficient_stock_rejected(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=0, price=10.0)
    src = await _make_branch(client, headers, "Main")
    dst = await _make_branch(client, headers, "Second")
    await _allocate(client, headers, src, pid, 5)

    resp = await client.post(
        "/api/v1/production/branches/transfer",
        json={"from_branch_id": src, "to_branch_id": dst, "product_id": pid, "quantity": 10},
        headers=headers,
    )
    assert resp.status_code == 400, resp.text

    # Nothing moved and no record was written (rolled back wholly).
    src_stock = await client.get(f"/api/v1/pos/branches/{src}/stock", headers=headers)
    assert {i["product_id"]: i["quantity"] for i in src_stock.json()["items"]}[pid] == 5
    async with db_manager.async_session_maker() as db:
        rows = (
            await db.execute(
                select(Stock_transfers).where(Stock_transfers.client_id == client_id)
            )
        ).scalars().all()
    assert len(rows) == 0


@pytest.mark.asyncio
async def test_transfer_is_owner_scoped(client):
    """A client cannot transfer using another client's branches (SEC-02)."""
    user_a, token_a, _ = await make_client_account(client)
    headers_a = auth_headers(token_a)
    pid_a = await add_product((await _client_id(user_a)), user_a["id"], quantity=0)
    src_a = await _make_branch(client, headers_a, "A-Main")
    dst_a = await _make_branch(client, headers_a, "A-Second")
    await _allocate(client, headers_a, src_a, pid_a, 30)

    # A second, unrelated client tries to move A's stock between A's branches.
    _user_b, token_b, _ = await make_client_account(client)
    headers_b = auth_headers(token_b)
    resp = await client.post(
        "/api/v1/production/branches/transfer",
        json={"from_branch_id": src_a, "to_branch_id": dst_a, "product_id": pid_a, "quantity": 5},
        headers=headers_b,
    )
    assert resp.status_code == 404, resp.text


async def _client_id(user):
    from models.clients import Clients

    async with db_manager.async_session_maker() as db:
        row = (
            await db.execute(select(Clients).where(Clients.user_id == user["id"]))
        ).scalar_one()
        return row.id
