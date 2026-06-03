"""F-034 — PO receive into the branch ledger, partial receipts, moving-average COGS.

The original receive flow incremented the client-level ``products.quantity`` (not
the per-branch ledger the POS deducts from), was all-or-nothing, and flat-overwrote
``cost_price``. These tests pin the corrected INV-07/INV-09 behavior:

- a branch-tagged receive lands stock in ``product_branch_stock`` (not client-level);
- successive partial receipts walk ``partially_received`` → ``received`` exactly once;
- over-receiving past the ordered quantity is rejected;
- ``cost_price`` is a moving average weighted by on-hand, not a flat overwrite.
"""
import json

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


async def _create_po(client, headers, items):
    resp = await client.post(
        "/api/v1/entities/purchase_orders",
        json={"order_number": "PO-T", "status": "ordered", "items_json": json.dumps(items)},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_po_receive_partial_into_branch_with_moving_average_cost(client):
    """Receive 5 @ C₁ then 5 @ C₂ → branch +10, status partial→received once, cost = weighted average."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=0, price=20.0)
    branch = await _make_branch(client, headers, "Main")

    po_id = await _create_po(client, headers, [{"product_id": pid, "quantity": 10, "cost": 8.0}])

    # First partial: 5 units @ cost 8 into the branch.
    r1 = await client.post(
        f"/api/v1/entities/purchase_orders/{po_id}/receive",
        json={"branch_id": branch, "lines": [{"product_id": pid, "quantity": 5, "cost": 8.0}]},
        headers=headers,
    )
    assert r1.status_code == 200, r1.text
    assert r1.json()["status"] == "partially_received"

    # Second partial completes the order: remaining 5 units @ cost 12.
    r2 = await client.post(
        f"/api/v1/entities/purchase_orders/{po_id}/receive",
        json={"branch_id": branch, "lines": [{"product_id": pid, "quantity": 5, "cost": 12.0}]},
        headers=headers,
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == "received"

    # Stock landed in the branch ledger (+10), NOT the client-level aggregate.
    bs = await client.get(f"/api/v1/pos/branches/{branch}/stock", headers=headers)
    assert {i["product_id"]: i["quantity"] for i in bs.json()["items"]}[pid] == 10

    async with db_manager.async_session_maker() as db:
        prod = (await db.execute(select(Products).where(Products.id == pid))).scalar_one()
        assert prod.quantity == 0  # branch receive does not touch the client-level aggregate
        # Moving average: (5*8 + 5*12) / 10 = 10.0, not a flat overwrite to 12.
        assert abs((prod.cost_price or 0) - 10.0) < 0.001

    # Idempotent: a fully-received PO cannot be received again.
    r3 = await client.post(
        f"/api/v1/entities/purchase_orders/{po_id}/receive", json={}, headers=headers
    )
    assert r3.status_code == 400


@pytest.mark.asyncio
async def test_po_receive_rejects_over_quantity(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=0, price=20.0)
    po_id = await _create_po(client, headers, [{"product_id": pid, "quantity": 3, "cost": 5.0}])

    r = await client.post(
        f"/api/v1/entities/purchase_orders/{po_id}/receive",
        json={"lines": [{"product_id": pid, "quantity": 5, "cost": 5.0}]},
        headers=headers,
    )
    assert r.status_code == 400

    # The over-receive was rejected wholesale — nothing was applied.
    async with db_manager.async_session_maker() as db:
        prod = (await db.execute(select(Products).where(Products.id == pid))).scalar_one()
        assert prod.quantity == 0


@pytest.mark.asyncio
async def test_po_receive_without_branch_updates_client_level_and_moving_average(client):
    """No branch_id → legacy client-level receive, still moving-average (not flat overwrite)."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=4, price=20.0)
    po_id = await _create_po(client, headers, [{"product_id": pid, "quantity": 6, "cost": 10.0}])

    r = await client.post(
        f"/api/v1/entities/purchase_orders/{po_id}/receive", json={}, headers=headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "received"

    async with db_manager.async_session_maker() as db:
        prod = (await db.execute(select(Products).where(Products.id == pid))).scalar_one()
        assert prod.quantity == 10  # 4 + 6 into client-level aggregate
        # Moving average with a prior cost of 0 on the 4 on-hand: (4*0 + 6*10) / 10 = 6.0.
        assert abs((prod.cost_price or 0) - 6.0) < 0.001
