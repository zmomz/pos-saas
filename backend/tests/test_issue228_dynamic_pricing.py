"""Issue #228 (M9·AI) — demand-driven dynamic-pricing slice.

The third slice of the AI/forecasting epic. Where ``/reports/sales-forecast``
projects revenue and ``/reports/inventory-forecast`` turns per-product demand
into a smart-reorder signal, this turns the *same* demand signal into a *pricing*
signal: it measures each product's recent sales velocity (units sold per day over
a lookback window), derives its days-of-cover (on-hand ÷ velocity), and proposes
a price adjustment:

* a fast mover whose stock will run out soon (low days-of-cover) is scarce, so the
  price can be *marked up* to protect margin and pace depletion;
* a slow mover sitting on excess stock (very high days-of-cover), or a product with
  on-hand but no recent sales at all, is *marked down* to stimulate demand and clear
  inventory;
* a balanced product is left alone (``hold``) and is not returned as a suggestion.

These tests prove the slice reaches through every layer (Transactions.items_json →
velocity accumulation → Products on-hand/price join → schema → router) and stays
honest about tenancy, held/voided exclusion, and physical-vs-digital stock.
"""
from datetime import datetime, timezone, timedelta

import json

from conftest import auth_headers, make_client_account
from core.database import db_manager
from models.products import Products
from models.transactions import Transactions


async def _add_product(client_id, user_id, name, quantity, price=10.0, *, is_digital=False):
    async with db_manager.async_session_maker() as db:
        p = Products(
            user_id=user_id,
            client_id=client_id,
            name=name,
            price=price,
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
                invoice_number=f"INV-DP-{client_id}-{status}-{days_ago}-{idx}",
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


async def test_scarce_fast_mover_is_marked_up(client):
    """High velocity + low stock → days-of-cover below the floor → markup."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    pid = await _add_product(client_id, user["id"], "Hot Item", quantity=5, price=20.0)
    # 60 units over the 30-day lookback → 2/day. Cover = 5 / 2 = 2.5 days (< floor 7).
    for i, days_ago in enumerate([1, 5, 9, 13, 17, 21]):
        await _seed_sale(client_id, user["id"], days_ago, [(pid, 10)], idx=i)

    resp = await client.get(
        "/api/v1/reports/dynamic-pricing?lookback=30&markup_pct=10&markdown_pct=15",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["method"] == "demand_elasticity"
    assert body["total"] == 1

    item = body["items"][0]
    assert item["product_id"] == pid
    assert item["signal"] == "markup"
    assert abs(item["avg_daily_units"] - 2.0) < 0.01
    assert abs(item["days_of_cover"] - 2.5) < 0.01
    assert abs(item["current_price"] - 20.0) < 0.001
    # +10% markup on a 20.00 price → 22.00, adjustment +10.
    assert abs(item["suggested_price"] - 22.0) < 0.001
    assert abs(item["adjustment_pct"] - 10.0) < 0.001


async def test_overstocked_slow_mover_is_marked_down(client):
    """Very high days-of-cover → markdown to clear excess inventory."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    pid = await _add_product(client_id, user["id"], "Dusty", quantity=1000, price=50.0)
    # 3 units over 30 days → 0.1/day → cover = 10000 days (>> ceiling 60).
    await _seed_sale(client_id, user["id"], 2, [(pid, 3)])

    resp = await client.get(
        "/api/v1/reports/dynamic-pricing?lookback=30&markup_pct=10&markdown_pct=15",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    item = resp.json()["items"][0]
    assert item["signal"] == "markdown"
    # −15% markdown on a 50.00 price → 42.50, adjustment −15.
    assert abs(item["suggested_price"] - 42.5) < 0.001
    assert abs(item["adjustment_pct"] - (-15.0)) < 0.001


async def test_dead_stock_with_no_recent_sales_is_marked_down(client):
    """On-hand but zero recent demand (infinite cover) → markdown."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    pid = await _add_product(client_id, user["id"], "Never Sells", quantity=8, price=30.0)
    # No sales at all in the window.

    resp = await client.get("/api/v1/reports/dynamic-pricing?lookback=30", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["product_id"] == pid
    assert item["signal"] == "markdown"
    assert item["days_of_cover"] is None


async def test_balanced_product_is_held_and_not_returned(client):
    """A product whose cover sits between the floor and ceiling gets no suggestion."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    pid = await _add_product(client_id, user["id"], "Steady", quantity=30, price=10.0)
    # 30 units over 30 days → 1/day → cover = 30 days (between floor 7 and ceiling 60).
    for i, days_ago in enumerate([2, 6, 10]):
        await _seed_sale(client_id, user["id"], days_ago, [(pid, 10)], idx=i)

    resp = await client.get("/api/v1/reports/dynamic-pricing?lookback=30", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] == 0


async def test_held_and_voided_sales_do_not_drive_pricing(client):
    """Parked/voided tickets are not demand and must not create a markup signal."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    pid = await _add_product(client_id, user["id"], "Mover", quantity=100, price=10.0)
    # Only 1 completed unit → 0.1/day → overstocked (markdown), NOT a scarce markup.
    await _seed_sale(client_id, user["id"], 1, [(pid, 1)], status="completed", idx=0)
    # A large held + voided demand would (wrongly) make it look scarce if counted.
    await _seed_sale(client_id, user["id"], 1, [(pid, 500)], status="held", idx=1)
    await _seed_sale(client_id, user["id"], 1, [(pid, 500)], status="voided", idx=2)

    resp = await client.get("/api/v1/reports/dynamic-pricing?lookback=30", headers=headers)
    assert resp.status_code == 200, resp.text
    item = resp.json()["items"][0]
    assert item["signal"] == "markdown"
    assert abs(item["avg_daily_units"] - (1 / 30)) < 0.001


async def test_digital_products_are_never_priced(client):
    """Digital products carry no physical stock, so scarcity pricing never applies."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    pid = await _add_product(
        client_id, user["id"], "eBook", quantity=0, price=10.0, is_digital=True
    )
    await _seed_sale(client_id, user["id"], 1, [(pid, 50)])

    resp = await client.get("/api/v1/reports/dynamic-pricing?lookback=30", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] == 0


async def test_dynamic_pricing_is_tenant_scoped(client):
    """One tenant's sales never leak into another tenant's pricing suggestions."""
    user_a, token_a, client_a = await make_client_account(client)
    user_b, token_b, client_b = await make_client_account(client)

    pid_b = await _add_product(client_b, user_b["id"], "B Widget", quantity=1, price=10.0)
    await _seed_sale(client_b, user_b["id"], 1, [(pid_b, 99)])

    resp = await client.get(
        "/api/v1/reports/dynamic-pricing?lookback=30", headers=auth_headers(token_a)
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] == 0
