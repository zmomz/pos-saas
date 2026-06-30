"""#220 (M4·Inventory multi-branch): central purchasing.

A multi-location chain buys centrally — one purchase order placed at HQ — and the
received goods are *distributed* across its branches in a single operation, each
branch's portion landing in the per-branch stock ledger (``product_branch_stock``)
the POS deducts from.

This is the central-purchasing slice of #220, building on the branch-aware PO
receive (INV-07): instead of receiving the whole PO into one branch, ``/distribute``
splits one central PO across many branches at once. The same outstanding-balance
guard and partial→received status walk as ``/receive`` apply across the *sum* of
the allocations.
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
        json={"order_number": "PO-C", "status": "ordered", "items_json": json.dumps(items)},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _branch_qty(client, headers, branch, product_id):
    bs = await client.get(f"/api/v1/pos/branches/{branch}/stock", headers=headers)
    assert bs.status_code == 200, bs.text
    return {i["product_id"]: i["quantity"] for i in bs.json()["items"]}.get(product_id, 0)


@pytest.mark.asyncio
async def test_distribute_central_po_across_two_branches(client):
    """A central PO of 10 units is split 6/4 across two branches in one call →
    each branch ledger is credited its portion, the PO is fully received, and the
    client-level aggregate is untouched (the goods live in the branch ledgers)."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=0, price=20.0)
    airport = await _make_branch(client, headers, "Airport")
    suburb = await _make_branch(client, headers, "Suburb")

    po_id = await _create_po(client, headers, [{"product_id": pid, "quantity": 10, "cost": 8.0}])

    resp = await client.post(
        f"/api/v1/entities/purchase_orders/{po_id}/distribute",
        json={
            "allocations": [
                {"branch_id": airport, "lines": [{"product_id": pid, "quantity": 6}]},
                {"branch_id": suburb, "lines": [{"product_id": pid, "quantity": 4}]},
            ]
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "received"

    assert await _branch_qty(client, headers, airport, pid) == 6
    assert await _branch_qty(client, headers, suburb, pid) == 4

    async with db_manager.async_session_maker() as db:
        prod = (await db.execute(select(Products).where(Products.id == pid))).scalar_one()
        assert prod.quantity == 0  # distribution lands in the branch ledgers, not the aggregate


@pytest.mark.asyncio
async def test_partial_distribution_then_completion(client):
    """A first distribution leaves a balance → partially_received; a second
    distribution of the rest completes the order exactly once."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=0, price=20.0)
    airport = await _make_branch(client, headers, "Airport")
    suburb = await _make_branch(client, headers, "Suburb")
    po_id = await _create_po(client, headers, [{"product_id": pid, "quantity": 10, "cost": 8.0}])

    r1 = await client.post(
        f"/api/v1/entities/purchase_orders/{po_id}/distribute",
        json={"allocations": [{"branch_id": airport, "lines": [{"product_id": pid, "quantity": 6}]}]},
        headers=headers,
    )
    assert r1.status_code == 200, r1.text
    assert r1.json()["status"] == "partially_received"
    assert await _branch_qty(client, headers, airport, pid) == 6

    r2 = await client.post(
        f"/api/v1/entities/purchase_orders/{po_id}/distribute",
        json={"allocations": [{"branch_id": suburb, "lines": [{"product_id": pid, "quantity": 4}]}]},
        headers=headers,
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == "received"
    assert await _branch_qty(client, headers, suburb, pid) == 4

    # Idempotent: a fully-received PO cannot be distributed again.
    r3 = await client.post(
        f"/api/v1/entities/purchase_orders/{po_id}/distribute",
        json={"allocations": [{"branch_id": airport, "lines": [{"product_id": pid, "quantity": 1}]}]},
        headers=headers,
    )
    assert r3.status_code == 400


@pytest.mark.asyncio
async def test_over_allocation_across_branches_is_rejected(client):
    """The sum across branches may not exceed the outstanding balance — the
    whole distribution is rejected and nothing lands in any branch ledger."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=0, price=20.0)
    airport = await _make_branch(client, headers, "Airport")
    suburb = await _make_branch(client, headers, "Suburb")
    po_id = await _create_po(client, headers, [{"product_id": pid, "quantity": 10, "cost": 8.0}])

    r = await client.post(
        f"/api/v1/entities/purchase_orders/{po_id}/distribute",
        json={
            "allocations": [
                {"branch_id": airport, "lines": [{"product_id": pid, "quantity": 7}]},
                {"branch_id": suburb, "lines": [{"product_id": pid, "quantity": 5}]},  # 7+5 > 10
            ]
        },
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert await _branch_qty(client, headers, airport, pid) == 0
    assert await _branch_qty(client, headers, suburb, pid) == 0


@pytest.mark.asyncio
async def test_distribute_is_owner_scoped(client):
    """A second tenant cannot distribute another tenant's central PO (SEC-02)."""
    user_a, token_a, cid_a = await make_client_account(client)
    headers_a = auth_headers(token_a)
    pid_a = await add_product(cid_a, user_a["id"], quantity=0, price=20.0)
    branch_a = await _make_branch(client, headers_a, "A-Airport")
    po_a = await _create_po(client, headers_a, [{"product_id": pid_a, "quantity": 5, "cost": 8.0}])

    _, token_b, _ = await make_client_account(client)
    headers_b = auth_headers(token_b)

    r = await client.post(
        f"/api/v1/entities/purchase_orders/{po_a}/distribute",
        json={"allocations": [{"branch_id": branch_a, "lines": [{"product_id": pid_a, "quantity": 5}]}]},
        headers=headers_b,
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_distribution_reweights_moving_average_cost(client):
    """cost_price is a moving average over the replenished destinations, weighted
    by their prior on-hand — not a flat overwrite."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=0, price=20.0)
    airport = await _make_branch(client, headers, "Airport")
    suburb = await _make_branch(client, headers, "Suburb")
    po_id = await _create_po(client, headers, [{"product_id": pid, "quantity": 10}])

    r = await client.post(
        f"/api/v1/entities/purchase_orders/{po_id}/distribute",
        json={
            "allocations": [
                {"branch_id": airport, "lines": [{"product_id": pid, "quantity": 5, "cost": 8.0}]},
                {"branch_id": suburb, "lines": [{"product_id": pid, "quantity": 5, "cost": 12.0}]},
            ]
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text

    async with db_manager.async_session_maker() as db:
        prod = (await db.execute(select(Products).where(Products.id == pid))).scalar_one()
        # Prior on-hand 0 at both branches: (5*8 + 5*12) / 10 = 10.0.
        assert abs((prod.cost_price or 0) - 10.0) < 0.001
