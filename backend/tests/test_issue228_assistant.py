"""Issue #228 (M9·AI) — in-app assistant tracer bullet.

The forecasting / smart-reorder / dynamic-pricing slices of #228 each answer a
single fixed question. The *assistant* is the conversational surface over the
same tenant data: the operator types a plain question and gets a grounded
answer computed from their own transactions and catalogue — no external LLM key
required for this first slice. ``method`` names the model (``rule_based`` today;
an LLM-backed router later) so the response is self-describing as it grows, and
``intent`` exposes how the question was routed so the surface is inspectable.

Every answer is tenant-scoped and client-only, exactly like the sibling
``/reports/*`` endpoints. Unroutable questions degrade to a helpful capability
list (HTTP 200), never a 400/500.
"""
from datetime import datetime, timezone, timedelta

from conftest import auth_headers, make_client_account
from core.database import db_manager
from models.products import Products
from models.transactions import Transactions


async def _seed_sale(client_id: int, user_id: str, *, days_ago: float, total: float,
                     items, status: str = "completed", idx: int = 0):
    """Insert one transaction carrying ``items`` (list of {product_id, quantity})."""
    import json as _json

    created = datetime.now(timezone.utc) - timedelta(days=days_ago, hours=1)
    async with db_manager.async_session_maker() as db:
        db.add(
            Transactions(
                user_id=user_id,
                client_id=client_id,
                invoice_number=f"INV-AS-{client_id}-{status}-{idx}",
                subtotal=total,
                vat_amount=0.0,
                discount_amount=0.0,
                total_amount=total,
                payment_method="cash",
                status=status,
                items_json=_json.dumps(items),
                created_at=created,
            )
        )
        await db.commit()


async def _seed_product(client_id: int, user_id: str, *, name: str, quantity: float,
                        reorder_point: int = 0, is_digital: bool = False,
                        price: float = 10.0) -> int:
    async with db_manager.async_session_maker() as db:
        p = Products(
            user_id=user_id,
            client_id=client_id,
            name=name,
            price=price,
            quantity=quantity,
            reorder_point=reorder_point,
            is_active=True,
            is_digital=is_digital,
        )
        db.add(p)
        await db.commit()
        await db.refresh(p)
        return p.id


async def test_assistant_names_the_top_selling_product(client):
    """"What's my best seller?" → the product with the most units sold."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    latte = await _seed_product(client_id, user["id"], name="Latte", quantity=50)
    muffin = await _seed_product(client_id, user["id"], name="Muffin", quantity=50)

    # Muffin outsells Latte over the window (12 units vs 5).
    await _seed_sale(client_id, user["id"], days_ago=1, total=100.0,
                     items=[{"product_id": latte, "quantity": 5}], idx=1)
    await _seed_sale(client_id, user["id"], days_ago=2, total=120.0,
                     items=[{"product_id": muffin, "quantity": 12}], idx=2)

    resp = await client.get(
        "/api/v1/assistant/query?q=what is my best selling product",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["method"] == "rule_based"
    assert body["intent"] == "top_product"
    assert body["data"]["product_id"] == muffin
    assert body["data"]["units_sold"] == 12
    assert "Muffin" in body["answer"]


async def test_assistant_reports_todays_net_sales(client):
    """"How much did I sell today?" → today's net takings; a credit note nets out."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    # Two sales today (300 + 200) and a credit note today (−50) → net 450.
    await _seed_sale(client_id, user["id"], days_ago=0, total=300.0, items=[], idx=1)
    await _seed_sale(client_id, user["id"], days_ago=0, total=200.0, items=[], idx=2)
    await _seed_sale(client_id, user["id"], days_ago=0, total=50.0, items=[],
                     status="credit_note", idx=3)
    # A sale a week ago must NOT count toward "today".
    await _seed_sale(client_id, user["id"], days_ago=7, total=999.0, items=[], idx=4)

    resp = await client.get(
        "/api/v1/assistant/query?q=how much did I sell today", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["intent"] == "sales_today"
    assert abs(body["data"]["net_sales"] - 450.0) < 0.01
    assert body["data"]["order_count"] == 2


async def test_assistant_lists_low_stock_products(client):
    """"Which products are low on stock?" → the reorder-point-aware low list."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    # Below its reorder point → low; well-stocked → not; digital → never low.
    await _seed_product(client_id, user["id"], name="Beans", quantity=2, reorder_point=10)
    await _seed_product(client_id, user["id"], name="Cups", quantity=500, reorder_point=10)
    await _seed_product(client_id, user["id"], name="Gift Card", quantity=0,
                        reorder_point=10, is_digital=True)

    resp = await client.get(
        "/api/v1/assistant/query?q=which products are low on stock", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["intent"] == "low_stock"
    assert body["data"]["count"] == 1
    names = [p["name"] for p in body["data"]["products"]]
    assert names == ["Beans"]
    assert "Beans" in body["answer"]


async def test_assistant_reports_average_order_value(client):
    """"What's my average order value?" → net 30-day takings ÷ order count."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    # Over the 30-day window: two orders (300 + 100) net to 400 across 2 orders
    # → AOV 200. A credit note nets the takings down but is not itself an order.
    await _seed_sale(client_id, user["id"], days_ago=3, total=300.0, items=[], idx=1)
    await _seed_sale(client_id, user["id"], days_ago=5, total=100.0, items=[], idx=2)
    await _seed_sale(client_id, user["id"], days_ago=6, total=40.0, items=[],
                     status="credit_note", idx=3)
    # A held ticket is not revenue, and a sale older than 30 days is out of window.
    await _seed_sale(client_id, user["id"], days_ago=1, total=999.0, items=[],
                     status="held", idx=4)
    await _seed_sale(client_id, user["id"], days_ago=40, total=999.0, items=[], idx=5)

    resp = await client.get(
        "/api/v1/assistant/query?q=what is my average order value", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["intent"] == "average_order"
    assert body["data"]["order_count"] == 2
    assert abs(body["data"]["net_sales"] - 360.0) < 0.01
    assert abs(body["data"]["average_order_value"] - 180.0) < 0.01
    assert "180" in body["answer"]


async def test_assistant_average_order_value_handles_no_sales(client):
    """No sales in the window → AOV is 0, not a divide-by-zero crash."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    resp = await client.get(
        "/api/v1/assistant/query?q=average basket size", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["intent"] == "average_order"
    assert body["data"]["order_count"] == 0
    assert body["data"]["average_order_value"] == 0.0


async def test_assistant_forecasts_next_weeks_sales(client):
    """"What's my sales forecast for next week?" → the 30-day daily average
    projected over the next 7 days (the assistant surface over the forecasting AI)."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    # Over the 30-day window: 300 + 600 = 900 in takings → 30/day average →
    # a 7-day projection of 210.
    await _seed_sale(client_id, user["id"], days_ago=5, total=300.0, items=[], idx=1)
    await _seed_sale(client_id, user["id"], days_ago=20, total=600.0, items=[], idx=2)
    # A held ticket is not revenue, and a sale older than 30 days is out of window.
    await _seed_sale(client_id, user["id"], days_ago=2, total=999.0, items=[],
                     status="held", idx=3)
    await _seed_sale(client_id, user["id"], days_ago=45, total=999.0, items=[], idx=4)

    resp = await client.get(
        "/api/v1/assistant/query?q=what is my sales forecast for next week",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["intent"] == "sales_forecast"
    assert body["data"]["lookback_days"] == 30
    assert body["data"]["horizon_days"] == 7
    assert abs(body["data"]["avg_daily_sales"] - 30.0) < 0.01
    assert abs(body["data"]["projected_sales"] - 210.0) < 0.01
    assert "210" in body["answer"]


async def test_assistant_forecast_handles_no_sales(client):
    """No sales in the window → a 0 forecast, not a crash or an empty answer."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    resp = await client.get(
        "/api/v1/assistant/query?q=how much will I sell next week", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["intent"] == "sales_forecast"
    assert body["data"]["projected_sales"] == 0.0
    assert body["data"]["avg_daily_sales"] == 0.0


async def test_assistant_suggests_smart_reorder_quantities(client):
    """"What should I reorder?" → velocity-driven reorder quantities, not the
    static low-stock list. A fast mover running thin gets a quantity sized to
    cover the target horizon; a well-stocked item is not suggested."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    # Beans: 5 on hand, sold 60 units over the window → 2/day → 14-day cover
    # target = 28 → suggest 28 − 5 = 23.
    beans = await _seed_product(client_id, user["id"], name="Beans", quantity=5)
    # Cups: 500 on hand, sold 30 units → 1/day → target 14, already covered → 0.
    cups = await _seed_product(client_id, user["id"], name="Cups", quantity=500)
    # Gift Card: digital → never a reorder candidate even at 0 stock.
    await _seed_product(client_id, user["id"], name="Gift Card", quantity=0,
                        is_digital=True)

    await _seed_sale(client_id, user["id"], days_ago=3, total=10.0,
                     items=[{"product_id": beans, "quantity": 60}], idx=1)
    await _seed_sale(client_id, user["id"], days_ago=4, total=10.0,
                     items=[{"product_id": cups, "quantity": 30}], idx=2)
    # A held ticket's units and a sale older than 30 days must not count toward
    # velocity (they'd inflate the suggested quantity).
    await _seed_sale(client_id, user["id"], days_ago=2, total=10.0,
                     items=[{"product_id": beans, "quantity": 999}],
                     status="held", idx=3)
    await _seed_sale(client_id, user["id"], days_ago=45, total=10.0,
                     items=[{"product_id": beans, "quantity": 999}], idx=4)

    resp = await client.get(
        "/api/v1/assistant/query?q=what should I reorder", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["intent"] == "smart_reorder"
    assert body["data"]["lookback_days"] == 30
    assert body["data"]["coverage_days"] == 14
    assert body["data"]["count"] == 1
    item = body["data"]["products"][0]
    assert item["product_id"] == beans
    assert item["on_hand"] == 5
    assert item["units_sold"] == 60
    assert abs(item["daily_velocity"] - 2.0) < 0.01
    assert item["suggested_reorder_qty"] == 23
    assert "Beans" in body["answer"]
    assert "23" in body["answer"]
    # The well-stocked and digital items are never suggested.
    assert cups not in [p["product_id"] for p in body["data"]["products"]]


async def test_assistant_smart_reorder_handles_nothing_to_reorder(client):
    """No sales (so no velocity) → nothing to reorder, not a crash or a bad list."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    await _seed_product(client_id, user["id"], name="Beans", quantity=5)

    resp = await client.get(
        "/api/v1/assistant/query?q=how much should I restock", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["intent"] == "smart_reorder"
    assert body["data"]["count"] == 0
    assert body["data"]["products"] == []


async def test_assistant_suggests_dynamic_price_markdowns(client):
    """"What should I discount?" → tiered markdown suggestions for overstocked
    slow-movers, sized to clear on-hand stock within the target window. The
    slower an item sells relative to its stock, the deeper the suggested cut; a
    fast mover that will clear on its own is never marked down."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    # Blazer: 120 on hand, sold 30 units over the window → 1/day → 120 days to
    # clear (> 90) → 20% markdown → 200 → 160.
    blazer = await _seed_product(client_id, user["id"], name="Blazer",
                                 quantity=120, price=200.0)
    # DeadStock: 25 on hand, no sales at all → never clears → deepest 25%
    # markdown → 40 → 30.
    dead = await _seed_product(client_id, user["id"], name="DeadStock",
                               quantity=25, price=40.0)
    # Bestseller: 10 on hand, sold 300 units → 10/day → clears in a day →
    # moving fine, never suggested.
    fast = await _seed_product(client_id, user["id"], name="Bestseller",
                               quantity=10, price=15.0)
    # Voucher: digital → no physical stock to clear, never a markdown candidate.
    await _seed_product(client_id, user["id"], name="Voucher", quantity=500,
                        price=25.0, is_digital=True)

    await _seed_sale(client_id, user["id"], days_ago=3, total=10.0,
                     items=[{"product_id": blazer, "quantity": 30}], idx=1)
    await _seed_sale(client_id, user["id"], days_ago=4, total=10.0,
                     items=[{"product_id": fast, "quantity": 300}], idx=2)
    # A held ticket's units and a sale older than 30 days must not resurrect the
    # dead item's velocity (they'd wrongly drop it off the markdown list).
    await _seed_sale(client_id, user["id"], days_ago=2, total=10.0,
                     items=[{"product_id": dead, "quantity": 999}],
                     status="held", idx=3)
    await _seed_sale(client_id, user["id"], days_ago=45, total=10.0,
                     items=[{"product_id": dead, "quantity": 999}], idx=4)

    resp = await client.get(
        "/api/v1/assistant/query?q=what should I discount", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["intent"] == "dynamic_pricing"
    assert body["data"]["lookback_days"] == 30
    assert body["data"]["clear_within_days"] == 30
    assert body["data"]["count"] == 2
    # Most-urgent (deepest markdown) first: the dead item outranks the slow one.
    first, second = body["data"]["products"]
    assert first["product_id"] == dead
    assert first["discount_pct"] == 25
    assert first["current_price"] == 40.0
    assert first["suggested_price"] == 30.0
    assert first["days_to_clear"] is None  # never clears at zero velocity
    assert second["product_id"] == blazer
    assert second["discount_pct"] == 20
    assert second["current_price"] == 200.0
    assert second["suggested_price"] == 160.0
    assert "DeadStock" in body["answer"]
    # The fast mover and the digital voucher are never marked down.
    ids = [p["product_id"] for p in body["data"]["products"]]
    assert fast not in ids


async def test_assistant_dynamic_pricing_handles_nothing_to_discount(client):
    """Everything selling through fast enough → no markdowns, not a crash."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    fast = await _seed_product(client_id, user["id"], name="Bestseller",
                               quantity=5, price=15.0)
    await _seed_sale(client_id, user["id"], days_ago=1, total=10.0,
                     items=[{"product_id": fast, "quantity": 300}], idx=1)

    resp = await client.get(
        "/api/v1/assistant/query?q=any pricing suggestions", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["intent"] == "dynamic_pricing"
    assert body["data"]["count"] == 0
    assert body["data"]["products"] == []


async def test_assistant_reports_week_over_week_trend(client):
    """"Is business up or down this week?" → this week's net takings compared to
    last week's, with a direction and a percent change (the assistant surface over
    a simple week-over-week trend)."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    # This week (0–7 days ago): 300 + 100 = 400 net; a credit note nets it down
    # to 360 like the other money metrics.
    await _seed_sale(client_id, user["id"], days_ago=1, total=300.0, items=[], idx=1)
    await _seed_sale(client_id, user["id"], days_ago=3, total=100.0, items=[], idx=2)
    await _seed_sale(client_id, user["id"], days_ago=2, total=40.0, items=[],
                     status="credit_note", idx=3)
    # Last week (7–14 days ago): 300 in takings → a +20% week-over-week move.
    await _seed_sale(client_id, user["id"], days_ago=9, total=300.0, items=[], idx=4)
    # A held ticket is not revenue, and a sale older than 14 days is out of both
    # windows (it must not become the baseline).
    await _seed_sale(client_id, user["id"], days_ago=5, total=999.0, items=[],
                     status="held", idx=5)
    await _seed_sale(client_id, user["id"], days_ago=20, total=999.0, items=[], idx=6)

    resp = await client.get(
        "/api/v1/assistant/query?q=is business up or down this week", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["intent"] == "sales_trend"
    assert body["data"]["period_days"] == 7
    assert abs(body["data"]["current_period_sales"] - 360.0) < 0.01
    assert abs(body["data"]["previous_period_sales"] - 300.0) < 0.01
    assert body["data"]["direction"] == "up"
    assert abs(body["data"]["change_pct"] - 20.0) < 0.01
    assert "up" in body["answer"].lower()
    assert "20" in body["answer"]


async def test_assistant_trend_handles_no_prior_week(client):
    """Sales this week but none last week → a graceful "no baseline" answer with a
    null percent change, not a divide-by-zero."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    await _seed_sale(client_id, user["id"], days_ago=1, total=150.0, items=[], idx=1)

    resp = await client.get(
        "/api/v1/assistant/query?q=how is business this week compared to last week",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["intent"] == "sales_trend"
    assert abs(body["data"]["current_period_sales"] - 150.0) < 0.01
    assert body["data"]["previous_period_sales"] == 0.0
    assert body["data"]["change_pct"] is None
    assert body["data"]["direction"] == "up"


async def test_assistant_unroutable_question_degrades_gracefully(client):
    """A question it can't map is an ``unknown`` answer with suggestions, not a 400/500."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    resp = await client.get(
        "/api/v1/assistant/query?q=what is the meaning of life", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["intent"] == "unknown"
    # It still offers a way forward: the capability list is populated.
    assert len(body["suggestions"]) >= 3


async def test_assistant_is_tenant_scoped(client):
    """One tenant's assistant never sees another tenant's sales."""
    user_a, token_a, client_a = await make_client_account(client)
    user_b, token_b, client_b = await make_client_account(client)

    # Tenant B has a runaway best-seller; tenant A has nothing.
    widget = await _seed_product(client_b, user_b["id"], name="Widget", quantity=50)
    await _seed_sale(client_b, user_b["id"], days_ago=1, total=500.0,
                     items=[{"product_id": widget, "quantity": 99}], idx=1)

    resp = await client.get(
        "/api/v1/assistant/query?q=what is my best selling product",
        headers=auth_headers(token_a),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["intent"] == "top_product"
    # Tenant A has no sales — B's Widget must not leak across the tenant boundary.
    assert body["data"] == {}
    assert "Widget" not in body["answer"]


async def _seed_sale_at(client_id: int, user_id: str, *, created_at, total: float,
                        status: str = "completed", idx: int = 0):
    """One transaction stamped at an explicit ``created_at`` (UTC) — the peak-hours
    intent buckets by the hour of the timestamp, so the tests need control over it
    (the relative ``_seed_sale`` only fixes the day)."""
    import json as _json

    async with db_manager.async_session_maker() as db:
        db.add(
            Transactions(
                user_id=user_id,
                client_id=client_id,
                invoice_number=f"INV-PH-{client_id}-{status}-{idx}",
                subtotal=total,
                vat_amount=0.0,
                discount_amount=0.0,
                total_amount=total,
                payment_method="cash",
                status=status,
                items_json=_json.dumps([]),
                created_at=created_at,
            )
        )
        await db.commit()


def _dow(dt):
    """0=Sunday .. 6=Saturday — matches Postgres extract('dow') and SQLite %w."""
    return int(dt.strftime("%w"))


async def test_assistant_reports_busiest_time(client):
    """"When are we busiest?" → the (day, hour) cell with the most orders, so a
    merchant knows when to staff up. Held tickets are not selling activity and
    never enter the heatmap."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    # A "hot" cell: three completed sales two days ago at 09:00.
    hot = (datetime.now(timezone.utc) - timedelta(days=2)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    await _seed_sale_at(client_id, user["id"], created_at=hot, total=10.0, idx=1)
    await _seed_sale_at(client_id, user["id"], created_at=hot, total=20.0, idx=2)
    await _seed_sale_at(client_id, user["id"], created_at=hot, total=30.0, idx=3)
    # A quieter cell: one sale three days ago at 14:00.
    quiet = (datetime.now(timezone.utc) - timedelta(days=3)).replace(
        hour=14, minute=0, second=0, microsecond=0
    )
    await _seed_sale_at(client_id, user["id"], created_at=quiet, total=99.0, idx=4)
    # A held ticket shares the hot cell but is parked, not sold — it must not tip
    # the count.
    await _seed_sale_at(client_id, user["id"], created_at=hot, total=999.0,
                        status="held", idx=5)

    resp = await client.get(
        "/api/v1/assistant/query?q=when are we busiest", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["intent"] == "peak_hours"
    assert body["data"]["total_orders"] == 4  # the held ticket is excluded
    busiest = body["data"]["busiest"]
    assert busiest["order_count"] == 3
    assert busiest["hour"] == 9
    assert busiest["day_of_week"] == _dow(hot)
    assert "3" in body["answer"]


async def test_assistant_busiest_time_handles_no_sales(client):
    """No sales in the window → a graceful "no busiest time" answer, not a crash on
    an empty grid."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    resp = await client.get(
        "/api/v1/assistant/query?q=what is my busiest hour", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["intent"] == "peak_hours"
    assert body["data"]["busiest"] is None
    assert body["data"]["total_orders"] == 0


async def test_assistant_rejects_non_clients(client):
    """A master (non-client) account cannot reach the assistant (403), like reports."""
    from conftest import make_master_account

    _user, token = await make_master_account(client)
    resp = await client.get(
        "/api/v1/assistant/query?q=what is my best selling product",
        headers=auth_headers(token),
    )
    assert resp.status_code == 403, resp.text
