"""Issue #228 (M9·AI) — inventory demand-forecast + smart-reorder slice.

The second slice of the AI/forecasting epic. Where ``/reports/sales-forecast``
projects *revenue*, this projects *demand per product* and turns it into a
smart-reorder signal: it measures each product's recent sales velocity (units
sold per day over a lookback window), projects the demand over a forecast
horizon, and compares that to on-hand stock to flag which products will run out
and how many units to reorder.

Unlike the existing ``/products/reorder-suggestions`` (a static on-hand ≤
reorder-point trigger), this is demand-driven: a fast mover with plenty of
nominal stock can still be flagged if velocity will burn through it before the
horizon, and a slow mover is left alone. That is the "smart reorder" scope item.

These tests prove the slice reaches through every layer (Transactions.items_json
→ velocity accumulation → Products on-hand join → schema → router) and stays
honest about tenancy, held/voided exclusion, and physical-vs-digital stock:

* velocity projection: units_sold / lookback → projected demand over the horizon,
  days-of-cover, a will-stock-out flag and a suggested reorder quantity;
* a well-stocked product is not flagged and suggests nothing;
* held/voided sales never inflate the velocity basis;
* digital products (no physical stock) are never forecast;
* one tenant's sales never leak into another's forecast.
"""
from datetime import datetime, timezone, timedelta

import json

from conftest import auth_headers, make_client_account
from core.database import db_manager
from models.products import Products
from models.transactions import Transactions


async def _add_product(client_id, user_id, name, quantity, *, is_digital=False):
    async with db_manager.async_session_maker() as db:
        p = Products(
            user_id=user_id,
            client_id=client_id,
            name=name,
            price=10.0,
            quantity=quantity,
            is_active=True,
            is_digital=is_digital,
        )
        db.add(p)
        await db.commit()
        await db.refresh(p)
        return p.id


async def _seed_sale(client_id, user_id, days_ago, items, *, status="completed", idx=0):
    """One transaction whose ``items_json`` carries ``[(product_id, qty), ...]``."""
    created = datetime.now(timezone.utc) - timedelta(days=days_ago, hours=1)
    payload = [
        {"product_id": pid, "quantity": qty, "price": 10.0, "name": f"P{pid}"}
        for pid, qty in items
    ]
    async with db_manager.async_session_maker() as db:
        db.add(
            Transactions(
                user_id=user_id,
                client_id=client_id,
                invoice_number=f"INV-IF-{client_id}-{status}-{days_ago}-{idx}",
                subtotal=10.0,
                vat_amount=0.0,
                discount_amount=0.0,
                total_amount=10.0,
                payment_method="cash",
                status=status,
                items_json=json.dumps(payload),
                created_at=created,
            )
        )
        await db.commit()


async def test_inventory_forecast_projects_velocity_and_smart_reorder(client):
    """60 units sold over a 30-day lookback → 2/day velocity, projected onto the horizon."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    pid = await _add_product(client_id, user["id"], "Fast Mover", quantity=10)
    # 6 sales of 10 units each, spread across the window → 60 units over 30 days.
    for i, days_ago in enumerate([1, 5, 9, 13, 17, 21]):
        await _seed_sale(client_id, user["id"], days_ago, [(pid, 10)], idx=i)

    resp = await client.get(
        "/api/v1/reports/inventory-forecast?lookback=30&horizon=14", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["method"] == "velocity_projection"
    assert body["lookback_days"] == 30
    assert body["horizon_days"] == 14
    assert body["total"] == 1

    item = body["items"][0]
    assert item["product_id"] == pid
    assert abs(item["avg_daily_units"] - 2.0) < 0.01
    assert item["on_hand"] == 10
    # 2/day × 14 days = 28 units projected demand; on-hand 10 → stock out.
    assert item["projected_demand"] == 28
    assert item["will_stock_out"] is True
    # Cover: 10 on-hand / 2 per day = 5 days.
    assert abs(item["days_of_cover"] - 5.0) < 0.01
    # Reorder enough to meet the shortfall: 28 demand − 10 on-hand = 18.
    assert item["suggested_reorder_quantity"] == 18


async def test_well_stocked_product_is_not_flagged(client):
    """A slow mover with ample stock will not stock out and suggests nothing."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    pid = await _add_product(client_id, user["id"], "Slow Mover", quantity=100)
    # 3 units over 30 days → 0.1/day; over a 14-day horizon ≈ 1.4 units ≪ 100.
    await _seed_sale(client_id, user["id"], 2, [(pid, 3)])

    resp = await client.get(
        "/api/v1/reports/inventory-forecast?lookback=30&horizon=14", headers=headers
    )
    assert resp.status_code == 200, resp.text
    item = resp.json()["items"][0]
    assert item["will_stock_out"] is False
    assert item["suggested_reorder_quantity"] == 0


async def test_held_and_voided_sales_do_not_inflate_velocity(client):
    """Parked and voided tickets are not demand and must not drive reorder."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    pid = await _add_product(client_id, user["id"], "Mover", quantity=5)
    await _seed_sale(client_id, user["id"], 1, [(pid, 4)], status="completed", idx=0)
    await _seed_sale(client_id, user["id"], 1, [(pid, 40)], status="held", idx=1)
    await _seed_sale(client_id, user["id"], 1, [(pid, 40)], status="voided", idx=2)

    resp = await client.get(
        "/api/v1/reports/inventory-forecast?lookback=10&horizon=10", headers=headers
    )
    assert resp.status_code == 200, resp.text
    item = resp.json()["items"][0]
    # Only the 4 completed units count: 4/10 = 0.4/day, not (4+80)/10.
    assert abs(item["avg_daily_units"] - 0.4) < 0.01


async def test_digital_products_are_never_forecast(client):
    """Digital products carry no physical stock, so they are never candidates."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    pid = await _add_product(client_id, user["id"], "eBook", quantity=0, is_digital=True)
    await _seed_sale(client_id, user["id"], 1, [(pid, 50)])

    resp = await client.get(
        "/api/v1/reports/inventory-forecast?lookback=30&horizon=14", headers=headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] == 0


async def test_inventory_forecast_is_tenant_scoped(client):
    """One tenant's sales never leak into another tenant's forecast."""
    user_a, token_a, client_a = await make_client_account(client)
    user_b, token_b, client_b = await make_client_account(client)

    pid_b = await _add_product(client_b, user_b["id"], "B Widget", quantity=1)
    await _seed_sale(client_b, user_b["id"], 1, [(pid_b, 99)])

    resp = await client.get(
        "/api/v1/reports/inventory-forecast?lookback=30&horizon=14",
        headers=auth_headers(token_a),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] == 0
