"""Phase 7 — Inventory report: on-hand valuation at cost + movements (F-070 / RPT-07).

A merchant could not pull a stock valuation at cost or a movement ledger — the only
stock figure was a dashboard stat valued at SALE price. These tests pin the corrected
behavior:

- the report values on-hand at ``cost_price`` (the money tied up in stock), never the
  sale price (the named catch-forever test);
- the movement feed surfaces a PO receipt and an inter-branch transfer over the window;
- the dashboard ``total_stock_value`` stat is corrected to value at cost.
"""
import json

import pytest

from conftest import (
    add_product,
    auth_headers,
    make_agent_account,
    make_client_account,
)


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


async def _create_po(client, headers, items):
    resp = await client.post(
        "/api/v1/entities/purchase_orders",
        json={"order_number": "PO-INV", "status": "ordered", "items_json": json.dumps(items)},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_inventory_valuation_uses_cost_price(client):
    """Named catch-forever test: on-hand is valued at COST, never sale price.

    10 units, cost 6, sale price 10 → stock value 60 (10×6), NOT 100 (10×10).
    """
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(
        client_id, user["id"], name="Mug", quantity=10, price=10.0, cost_price=6.0
    )

    resp = await client.get("/api/v1/reports/inventory?days=30", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["total_valuation"] == 60.0   # cost basis, not the 100.0 retail value
    assert body["total_quantity"] == 10.0
    row = next(r for r in body["by_product"] if r["product_id"] == pid)
    assert row["cost_price"] == 6.0
    assert row["stock_value"] == 60.0


@pytest.mark.asyncio
async def test_movements_show_receipt_and_transfer(client):
    """Named catch-forever test: a PO receipt and a transfer appear in movements."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(
        client_id, user["id"], name="Bolt", quantity=0, price=4.0, cost_price=2.0
    )
    src = await _make_branch(client, headers, "Main")
    dst = await _make_branch(client, headers, "Second")

    # Receive a PO into the source branch → a receipt movement.
    po_id = await _create_po(client, headers, [{"product_id": pid, "quantity": 20, "cost": 2.0}])
    r = await client.post(
        f"/api/v1/entities/purchase_orders/{po_id}/receive",
        json={"branch_id": src, "lines": [{"product_id": pid, "quantity": 20, "cost": 2.0}]},
        headers=headers,
    )
    assert r.status_code == 200, r.text

    # Move 5 to the destination branch → a transfer movement.
    t = await client.post(
        "/api/v1/production/branches/transfer",
        json={"from_branch_id": src, "to_branch_id": dst, "product_id": pid, "quantity": 5},
        headers=headers,
    )
    assert t.status_code == 200, t.text

    resp = await client.get("/api/v1/reports/inventory", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    types = {m["type"] for m in body["movements"]}
    assert "receipt" in types
    assert "transfer" in types

    receipt = next(m for m in body["movements"] if m["type"] == "receipt")
    assert receipt["product_id"] == pid
    assert receipt["quantity"] == 20.0
    assert receipt["reference"] == "PO-INV"

    transfer = next(m for m in body["movements"] if m["type"] == "transfer")
    assert transfer["product_id"] == pid
    assert transfer["quantity"] == 5.0
    assert "Main" in transfer["reference"] and "Second" in transfer["reference"]

    # Per-branch valuation at cost reflects the ledger (source 15 + dest 5 → cost 2).
    by_branch = {b["branch_id"]: b for b in body["by_branch"]}
    assert by_branch[src]["stock_value"] == 30.0   # 15 × 2
    assert by_branch[dst]["stock_value"] == 10.0   # 5 × 2


@pytest.mark.asyncio
async def test_dashboard_stock_value_is_at_cost(client):
    """The dashboard inventory stat values stock at cost, not sale price (the fixed bug)."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await add_product(
        client_id, user["id"], name="Plate", quantity=10, price=25.0, cost_price=7.0
    )
    await _make_branch(client, headers, "Main")

    resp = await client.get("/api/v1/production/branches/inventory", headers=headers)
    assert resp.status_code == 200, resp.text
    branches = resp.json()["branches"]
    assert branches, "expected at least one branch row"
    # 10 × cost 7 = 70, not 10 × price 25 = 250.
    assert branches[0]["total_stock_value"] == 70.0


@pytest.mark.asyncio
async def test_inventory_csv_export(client):
    """CSV export carries the valuation and movement sections."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await add_product(
        client_id, user["id"], name="Cup", quantity=5, price=8.0, cost_price=3.0
    )

    resp = await client.get("/api/v1/reports/inventory", headers=headers)
    body = resp.json()
    csv_text = body["csv_content"]
    assert "Inventory valuation at cost" in csv_text
    assert "Stock movements" in csv_text
    assert "Cup" in csv_text


@pytest.mark.asyncio
async def test_inventory_owner_scoped(client):
    """SEC-02: a client sees only its own stock; an agent is 403."""
    user_a, token_a, client_a = await make_client_account(client)
    user_b, token_b, client_b = await make_client_account(client)

    await add_product(client_a, user_a["id"], name="A", quantity=10, price=10.0, cost_price=5.0)
    await add_product(client_b, user_b["id"], name="B", quantity=10, price=10.0, cost_price=9.0)

    resp_a = await client.get("/api/v1/reports/inventory", headers=auth_headers(token_a))
    body_a = resp_a.json()
    assert body_a["total_valuation"] == 50.0  # only A's 10×5, never B's 10×9

    _, agent_token, _ = await make_agent_account(client)
    resp_agent = await client.get(
        "/api/v1/reports/inventory", headers=auth_headers(agent_token)
    )
    assert resp_agent.status_code == 403, resp_agent.text
