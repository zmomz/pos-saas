"""Phase 7 — profit / COGS / margin report + dead stock (F-068 / RPT-04, INV-09).

A merchant must be able to see gross profit and margin, not just revenue. This
report breaks revenue / COGS / gross profit / margin % down by item and category
over a window, and lists dead stock (on-hand > 0, no sale in N days).

The defining property (the catch-forever test): margin is **stable** because each
sale line snapshots its product cost at sale time — changing the product cost
later must NOT rewrite the historical COGS the report shows.
"""
from sqlalchemy import update

from conftest import (
    add_product,
    auth_headers,
    make_agent_account,
    make_client_account,
)
from core.database import db_manager
from models.products import Products


async def _sell(client, headers, pid, name, price, qty):
    resp = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": name, "price": price, "quantity": qty}],
            "payment_method": "cash",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _set_cost(pid, cost):
    async with db_manager.async_session_maker() as db:
        await db.execute(update(Products).where(Products.id == pid).values(cost_price=cost))
        await db.commit()


async def test_margin_report_uses_cogs(client):
    """Named catch-forever test: revenue 100, COGS 60, gross 40 — from the snapshot.

    Sell 10 units @ 10 of a product costing 6 → revenue 100, COGS 60, gross 40,
    margin 40%. Then change the product cost to 9 and re-run the report: COGS stays
    60 because the report reads the cost snapshotted onto the sale line, not the
    current product cost.
    """
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(
        client_id, user["id"], name="Widget", quantity=50, price=10.0, cost_price=6.0
    )

    await _sell(client, headers, pid, "Widget", 10.0, 10)

    resp = await client.get("/api/v1/reports/profit-margin?days=30", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["totals"]["revenue"] == 100.0
    assert body["totals"]["cogs"] == 60.0
    assert body["totals"]["gross_profit"] == 40.0
    assert body["totals"]["margin_pct"] == 40.0

    item = next(r for r in body["by_item"] if r["key"] == str(pid))
    assert item["revenue"] == 100.0
    assert item["cogs"] == 60.0
    assert item["gross_profit"] == 40.0

    # The cost moves AFTER the sale — historical margin must not move with it.
    await _set_cost(pid, 9.0)
    resp2 = await client.get("/api/v1/reports/profit-margin?days=30", headers=headers)
    assert resp2.status_code == 200, resp2.text
    body2 = resp2.json()
    assert body2["totals"]["cogs"] == 60.0, "report must use the sale-time cost snapshot"
    assert body2["totals"]["gross_profit"] == 40.0


async def test_report_breaks_down_by_category(client):
    """Revenue/COGS roll up per category, and the CSV carries the rows."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    async def _add(name, price, cost, category):
        async with db_manager.async_session_maker() as db:
            p = Products(
                user_id=user["id"], client_id=client_id, name=name, price=price,
                cost_price=cost, quantity=100, category=category, is_active=True,
            )
            db.add(p)
            await db.commit()
            await db.refresh(p)
            return p.id

    a = await _add("Cola", 5.0, 2.0, "Drinks")
    b = await _add("Water", 3.0, 1.0, "Drinks")
    c = await _add("Chips", 4.0, 3.0, "Snacks")

    await _sell(client, headers, a, "Cola", 5.0, 10)   # rev 50, cogs 20
    await _sell(client, headers, b, "Water", 3.0, 10)  # rev 30, cogs 10
    await _sell(client, headers, c, "Chips", 4.0, 5)   # rev 20, cogs 15

    resp = await client.get("/api/v1/reports/profit-margin", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    cats = {r["name"]: r for r in body["by_category"]}
    assert cats["Drinks"]["revenue"] == 80.0
    assert cats["Drinks"]["cogs"] == 30.0
    assert cats["Drinks"]["gross_profit"] == 50.0
    assert cats["Snacks"]["revenue"] == 20.0
    assert cats["Snacks"]["cogs"] == 15.0

    assert body["totals"]["revenue"] == 100.0
    assert body["totals"]["cogs"] == 45.0
    # CSV export works and carries the category section.
    assert "Drinks" in body["csv_content"]
    assert "CATEGORY" in body["csv_content"]


async def test_dead_stock_lists_unsold_onhand(client):
    """A product with on-hand stock and no sale in the window is dead stock."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    sold = await add_product(client_id, user["id"], name="Mover", quantity=20, price=10.0, cost_price=4.0)
    idle = await add_product(client_id, user["id"], name="Slow", quantity=8, price=10.0, cost_price=5.0)
    empty = await add_product(client_id, user["id"], name="Empty", quantity=0, price=10.0, cost_price=5.0)

    await _sell(client, headers, sold, "Mover", 10.0, 1)

    resp = await client.get("/api/v1/reports/profit-margin", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    dead_ids = {d["product_id"] for d in body["dead_stock"]}
    assert idle in dead_ids          # on-hand > 0 and never sold → dead stock
    assert sold not in dead_ids      # sold in the window → not dead
    assert empty not in dead_ids     # on-hand 0 → not dead stock

    slow = next(d for d in body["dead_stock"] if d["product_id"] == idle)
    assert slow["quantity"] == 8.0
    assert slow["stock_value"] == 40.0  # 8 * 5.0


async def test_refund_nets_revenue_and_cogs(client):
    """A credit note reverses both revenue and COGS on the report."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Gadget", quantity=50, price=10.0, cost_price=6.0)

    sale = await _sell(client, headers, pid, "Gadget", 10.0, 10)
    txn_id = sale["id"]

    # Refund 4 units → credit note nets revenue down by 40 and COGS by 24.
    refund = await client.post(
        f"/api/v1/pos/transactions/{txn_id}/refund",
        json={"lines": [{"product_id": pid, "quantity": 4}]},
        headers=headers,
    )
    assert refund.status_code == 200, refund.text

    resp = await client.get("/api/v1/reports/profit-margin", headers=headers)
    body = resp.json()
    assert body["totals"]["revenue"] == 60.0   # 100 - 40
    assert body["totals"]["cogs"] == 36.0       # 60 - 24
    assert body["totals"]["gross_profit"] == 24.0


async def test_profit_margin_owner_scoped(client):
    """SEC-02: one client never sees another's figures; an agent is 403."""
    user_a, token_a, client_a = await make_client_account(client)
    user_b, token_b, client_b = await make_client_account(client)

    pa = await add_product(client_a, user_a["id"], name="A", quantity=50, price=10.0, cost_price=6.0)
    pb = await add_product(client_b, user_b["id"], name="B", quantity=50, price=20.0, cost_price=5.0)
    await _sell(client, auth_headers(token_a), pa, "A", 10.0, 10)
    await _sell(client, auth_headers(token_b), pb, "B", 20.0, 10)

    resp_a = await client.get("/api/v1/reports/profit-margin", headers=auth_headers(token_a))
    body_a = resp_a.json()
    assert body_a["totals"]["revenue"] == 100.0  # only A's sale, never B's 200

    _, agent_token, _ = await make_agent_account(client)
    resp_agent = await client.get("/api/v1/reports/profit-margin", headers=auth_headers(agent_token))
    assert resp_agent.status_code == 403, resp_agent.text
