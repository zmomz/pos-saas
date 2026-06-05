"""Phase 6 (deferred): per-branch stock ledger.

A sale tagged with a branch_id deducts that branch's stock only — sibling
branches and the client-level aggregate are untouched — and a refund restores
the branch's stock.
"""
import pytest
from sqlalchemy import select

from conftest import add_product, auth_headers, make_client_account
from core.database import db_manager
from models.products import Products


async def _make_branch(client, headers, name):
    resp = await client.post(
        "/api/v1/entities/branches",
        json={"name": name, "is_active": True},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _set_stock(client, headers, branch_id, product_id, qty):
    resp = await client.put(
        f"/api/v1/pos/branches/{branch_id}/stock",
        json={"product_id": product_id, "quantity": qty},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_branch_sale_deducts_only_that_branch(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=100, price=10.0)

    branch_a = await _make_branch(client, headers, "Branch A")
    branch_b = await _make_branch(client, headers, "Branch B")
    await _set_stock(client, headers, branch_a, pid, 10)
    await _set_stock(client, headers, branch_b, pid, 20)

    # Sell 3 in branch A.
    resp = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Cola", "price": 10.0, "quantity": 3}],
            "payment_method": "cash",
            "branch_id": branch_a,
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    # Branch A down to 7; Branch B unchanged at 20.
    a = await client.get(f"/api/v1/pos/branches/{branch_a}/stock", headers=headers)
    b = await client.get(f"/api/v1/pos/branches/{branch_b}/stock", headers=headers)
    a_qty = {i["product_id"]: i["quantity"] for i in a.json()["items"]}[pid]
    b_qty = {i["product_id"]: i["quantity"] for i in b.json()["items"]}[pid]
    assert a_qty == 7
    assert b_qty == 20

    # Client-level aggregate stock is untouched by a branch-tagged sale.
    async with db_manager.async_session_maker() as db:
        prod = (await db.execute(select(Products).where(Products.id == pid))).scalar_one()
        assert prod.quantity == 100


@pytest.mark.asyncio
async def test_branch_insufficient_stock_rejected(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=100, price=10.0)
    branch_a = await _make_branch(client, headers, "Branch A")
    await _set_stock(client, headers, branch_a, pid, 2)

    resp = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Cola", "price": 10.0, "quantity": 5}],
            "payment_method": "cash",
            "branch_id": branch_a,
        },
        headers=headers,
    )
    assert resp.status_code == 400
    # Stock unchanged after the rejected sale.
    a = await client.get(f"/api/v1/pos/branches/{branch_a}/stock", headers=headers)
    assert {i["product_id"]: i["quantity"] for i in a.json()["items"]}[pid] == 2


@pytest.mark.asyncio
async def test_branch_inventory_view_uses_ledger(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    # Stock is valued at COST (F-070): cost 3.0, sale price 5.0.
    pid = await add_product(client_id, user["id"], quantity=100, price=5.0, cost_price=3.0)
    branch_a = await _make_branch(client, headers, "Branch A")
    await _set_stock(client, headers, branch_a, pid, 4)

    resp = await client.get(
        f"/api/v1/production/branches/inventory?branch_id={branch_a}", headers=headers
    )
    assert resp.status_code == 200, resp.text
    branches = resp.json()["branches"]
    assert len(branches) == 1
    # 4 units (from the ledger, not the 100 client-level façade) × cost 3.0 = 12.0
    # — valued at cost (F-070), never the 5.0 sale price.
    assert abs(branches[0]["total_stock_value"] - 12.0) < 0.01
