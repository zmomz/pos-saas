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
from models.expenses import Expenses
from models.products import Products
from models.transactions import Transactions


async def _seed_expense(client_id: int, user_id: str, *, days_ago: float,
                        amount: float, category: str, idx: int = 0):
    """Insert one recorded expense stamped ``days_ago`` days back (UTC)."""
    created = datetime.now(timezone.utc) - timedelta(days=days_ago, hours=1)
    async with db_manager.async_session_maker() as db:
        db.add(
            Expenses(
                user_id=user_id,
                client_id=client_id,
                category=category,
                amount=amount,
                description=f"exp-{idx}",
                created_at=created,
            )
        )
        await db.commit()


async def _seed_sale(client_id: int, user_id: str, *, days_ago: float, total: float,
                     items, status: str = "completed", idx: int = 0,
                     payment_method: str = "cash", vat: float = 0.0,
                     discount: float = 0.0,
                     customer_name=None, customer_phone=None):
    """Insert one transaction carrying ``items`` (list of {product_id, quantity})."""
    import json as _json

    created = datetime.now(timezone.utc) - timedelta(days=days_ago, hours=1)
    async with db_manager.async_session_maker() as db:
        db.add(
            Transactions(
                user_id=user_id,
                client_id=client_id,
                invoice_number=f"INV-AS-{client_id}-{status}-{payment_method}-{idx}",
                subtotal=total - vat,
                vat_amount=vat,
                discount_amount=discount,
                total_amount=total,
                payment_method=payment_method,
                status=status,
                items_json=_json.dumps(items),
                customer_name=customer_name,
                customer_phone=customer_phone,
                created_at=created,
            )
        )
        await db.commit()


async def _seed_product(client_id: int, user_id: str, *, name: str, quantity: float,
                        reorder_point: int = 0, is_digital: bool = False,
                        price: float = 10.0, cost_price=None,
                        is_active: bool = True) -> int:
    async with db_manager.async_session_maker() as db:
        p = Products(
            user_id=user_id,
            client_id=client_id,
            name=name,
            price=price,
            cost_price=cost_price,
            quantity=quantity,
            reorder_point=reorder_point,
            is_active=is_active,
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


async def test_assistant_markdown_never_prices_below_cost(client):
    """A tiered markdown that would dip under cost is floored at cost, not a loss."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    # Dead stock (no sales in window) → deepest 25% tier. price 40, cost 35: a raw
    # −25% lands at 30.00, BELOW the 35.00 cost. It must clamp to cost.
    dead = await _seed_product(client_id, user["id"], name="ThinDead",
                               quantity=20, price=40.0, cost_price=35.0)

    resp = await client.get(
        "/api/v1/assistant/query?q=what should I discount", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["intent"] == "dynamic_pricing"
    item = body["data"]["products"][0]
    assert item["product_id"] == dead
    assert item["cost_price"] == 35.0
    assert item["margin_floored"] is True
    assert item["suggested_price"] == 35.0  # clamped to cost, not the 30.00 raw markdown
    # discount_pct reflects the ACTUAL applied cut (40→35 = 12.5%), not the 25 nominal.
    assert item["discount_pct"] == 12.5


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


async def test_assistant_forecasts_which_products_will_run_out(client):
    """"Which products will run out soon?" → a velocity/days-of-cover forecast,
    distinct from the reorder-quantity and static low-stock answers. A fast mover
    that will burn through its on-hand within the horizon is listed with a
    days-of-cover estimate; a well-stocked slow mover is not."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    # Beans: 6 on hand, sold 60 units over the window → 2/day → 3 days of cover;
    # projected 14-day demand (28) far exceeds on-hand → will run out.
    beans = await _seed_product(client_id, user["id"], name="Beans", quantity=6)
    # Cups: 500 on hand, sold 30 → 1/day → 14-day demand (14) < on-hand → safe.
    cups = await _seed_product(client_id, user["id"], name="Cups", quantity=500)
    # Gift Card: digital → never a stock-out candidate even at 0 stock.
    await _seed_product(client_id, user["id"], name="Gift Card", quantity=0,
                        is_digital=True)

    await _seed_sale(client_id, user["id"], days_ago=3, total=10.0,
                     items=[{"product_id": beans, "quantity": 60}], idx=1)
    await _seed_sale(client_id, user["id"], days_ago=4, total=10.0,
                     items=[{"product_id": cups, "quantity": 30}], idx=2)
    # A held ticket and an out-of-window sale must not inflate velocity.
    await _seed_sale(client_id, user["id"], days_ago=2, total=10.0,
                     items=[{"product_id": beans, "quantity": 999}],
                     status="held", idx=3)
    await _seed_sale(client_id, user["id"], days_ago=45, total=10.0,
                     items=[{"product_id": beans, "quantity": 999}], idx=4)

    resp = await client.get(
        "/api/v1/assistant/query?q=which products will run out soon", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["intent"] == "stock_out"
    assert body["data"]["lookback_days"] == 30
    assert body["data"]["horizon_days"] == 14
    assert body["data"]["count"] == 1
    item = body["data"]["products"][0]
    assert item["product_id"] == beans
    assert item["on_hand"] == 6
    assert abs(item["daily_velocity"] - 2.0) < 0.01
    assert abs(item["days_of_cover"] - 3.0) < 0.01
    assert "Beans" in body["answer"]
    # The well-stocked and digital items never appear.
    assert cups not in [p["product_id"] for p in body["data"]["products"]]


async def test_assistant_stock_out_handles_nothing_at_risk(client):
    """No sales (so no velocity) → nothing will run out, not a crash or bad list."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    await _seed_product(client_id, user["id"], name="Beans", quantity=5)

    resp = await client.get(
        "/api/v1/assistant/query?q=when will my stock run out", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["intent"] == "stock_out"
    assert body["data"]["count"] == 0
    assert body["data"]["products"] == []


async def test_assistant_names_the_most_profitable_product(client):
    """"Which product is most profitable?" → the product contributing the most
    *gross profit* (units sold × per-unit margin), not the most units or revenue.

    Margin is ``price - cost_price``; a cheap high-volume item can out-earn a
    pricey low-volume one. Products with no ``cost_price`` have no computable
    margin and are excluded, even if they sell heavily. Held/voided tickets and
    out-of-window sales never count toward the profit total.
    """
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    # Coffee: margin 6/unit × 10 units = 60 profit.
    coffee = await _seed_product(client_id, user["id"], name="Coffee", quantity=100,
                                 price=10.0, cost_price=4.0)
    # Muffin: margin 4/unit × 20 units = 80 profit → the winner (most total profit,
    # though a lower per-unit margin than Coffee).
    muffin = await _seed_product(client_id, user["id"], name="Muffin", quantity=100,
                                 price=5.0, cost_price=1.0)
    # Mystery: no cost_price → margin unknown → excluded despite heavy sales.
    mystery = await _seed_product(client_id, user["id"], name="Mystery", quantity=100,
                                  price=100.0, cost_price=None)

    await _seed_sale(client_id, user["id"], days_ago=2, total=100.0,
                     items=[{"product_id": coffee, "quantity": 10}], idx=1)
    await _seed_sale(client_id, user["id"], days_ago=3, total=100.0,
                     items=[{"product_id": muffin, "quantity": 20}], idx=2)
    await _seed_sale(client_id, user["id"], days_ago=4, total=100.0,
                     items=[{"product_id": mystery, "quantity": 100}], idx=3)
    # A held ticket and an out-of-window sale must not inflate the profit total.
    await _seed_sale(client_id, user["id"], days_ago=1, total=100.0,
                     items=[{"product_id": muffin, "quantity": 999}],
                     status="held", idx=4)
    await _seed_sale(client_id, user["id"], days_ago=45, total=100.0,
                     items=[{"product_id": coffee, "quantity": 999}], idx=5)

    resp = await client.get(
        "/api/v1/assistant/query?q=which product is most profitable", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["intent"] == "top_margin"
    data = body["data"]
    assert data["product_id"] == muffin
    assert data["units_sold"] == 20
    assert abs(data["unit_margin"] - 4.0) < 0.01
    assert abs(data["gross_profit"] - 80.0) < 0.01
    assert "Muffin" in body["answer"]
    # The no-cost product is never crowned, however much it sells.
    assert data["product_id"] != mystery


async def test_assistant_top_margin_without_cost_data_degrades_gracefully(client):
    """No cost prices anywhere (so no computable margin) → a helpful nudge, HTTP
    200, empty data — never a crash or a bogus winner."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    widget = await _seed_product(client_id, user["id"], name="Widget", quantity=100,
                                 price=10.0, cost_price=None)
    await _seed_sale(client_id, user["id"], days_ago=2, total=100.0,
                     items=[{"product_id": widget, "quantity": 10}], idx=1)

    resp = await client.get(
        "/api/v1/assistant/query?q=what is my highest margin product", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["intent"] == "top_margin"
    assert body["data"] == {}
    assert "cost" in body["answer"].lower()


async def test_assistant_flags_dead_stock(client):
    """"Which products aren't selling?" → dead stock: items with stock on hand but
    no sale in the trailing window, ranked by the capital tied up in them. Distinct
    from ``low_stock`` (which are *low*) and ``dynamic_pricing`` (what to *discount*):
    this names what's sitting idle. A recently-sold item is not dead; a digital item
    (no physical stock) never appears; a zero-on-hand item can't be dead stock; an
    out-of-window or held/voided sale does not count as "recently sold"."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    # Latte: 10 on hand, sold 3 days ago → moving, NOT dead.
    latte = await _seed_product(client_id, user["id"], name="Latte", quantity=10,
                                cost_price=4.0)
    # Mug: 20 on hand, never sold → dead. Capital tied up = 20 × 5 = 100.
    mug = await _seed_product(client_id, user["id"], name="Mug", quantity=20,
                              cost_price=5.0)
    # Poster: 3 on hand, only sale is 45 days ago (out of window) → dead. 3 × 8 = 24.
    poster = await _seed_product(client_id, user["id"], name="Poster", quantity=3,
                                 cost_price=8.0)
    # Gift Card: digital → excluded even though it carries a quantity.
    await _seed_product(client_id, user["id"], name="Gift Card", quantity=5,
                        is_digital=True, cost_price=1.0)
    # Sold Out: 0 on hand → can't be dead stock (nothing sitting there).
    await _seed_product(client_id, user["id"], name="Sold Out", quantity=0,
                        cost_price=3.0)

    await _seed_sale(client_id, user["id"], days_ago=3, total=10.0,
                     items=[{"product_id": latte, "quantity": 2}], idx=1)
    await _seed_sale(client_id, user["id"], days_ago=45, total=10.0,
                     items=[{"product_id": poster, "quantity": 1}], idx=2)
    # A held ticket for Mug must not count as a sale → Mug stays dead.
    await _seed_sale(client_id, user["id"], days_ago=2, total=10.0,
                     items=[{"product_id": mug, "quantity": 1}],
                     status="held", idx=3)

    resp = await client.get(
        "/api/v1/assistant/query?q=which products aren't selling", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["intent"] == "dead_stock"
    assert body["data"]["window_days"] == 30
    assert body["data"]["count"] == 2
    ids = [p["product_id"] for p in body["data"]["products"]]
    assert latte not in ids
    # Ranked by capital tied up: Mug (100) before Poster (24).
    assert ids == [mug, poster]
    first = body["data"]["products"][0]
    assert first["product_id"] == mug
    assert first["on_hand"] == 20
    assert abs(first["stock_value"] - 100.0) < 0.01
    assert "Mug" in body["answer"]


async def test_assistant_dead_stock_handles_all_moving(client):
    """Everything on hand has sold recently → no dead stock, a reassuring message
    and empty data, never a crash."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    latte = await _seed_product(client_id, user["id"], name="Latte", quantity=10,
                                cost_price=4.0)
    await _seed_sale(client_id, user["id"], days_ago=1, total=10.0,
                     items=[{"product_id": latte, "quantity": 2}], idx=1)

    resp = await client.get(
        "/api/v1/assistant/query?q=which products are dead stock", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["intent"] == "dead_stock"
    assert body["data"]["count"] == 0
    assert body["data"]["products"] == []


async def test_assistant_reports_payment_mix(client):
    """"How do my customers pay?" → a tender breakdown over the last 30 days,
    ranked by net revenue, with the dominant tender named. Credit notes net
    against their own tender; held/voided tickets are not selling activity."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    # Card takes the most money (500), cash next (300 gross − 50 refund = 250).
    await _seed_sale(client_id, user["id"], days_ago=2, total=300.0, items=[],
                     payment_method="card", idx=1)
    await _seed_sale(client_id, user["id"], days_ago=3, total=200.0, items=[],
                     payment_method="card", idx=2)
    await _seed_sale(client_id, user["id"], days_ago=4, total=300.0, items=[],
                     payment_method="cash", idx=3)
    # A cash refund nets that tender down but is not itself an order.
    await _seed_sale(client_id, user["id"], days_ago=5, total=50.0, items=[],
                     payment_method="cash", status="credit_note", idx=4)
    # Held/voided and out-of-window sales must never count.
    await _seed_sale(client_id, user["id"], days_ago=1, total=999.0, items=[],
                     payment_method="card", status="held", idx=5)
    await _seed_sale(client_id, user["id"], days_ago=1, total=999.0, items=[],
                     payment_method="cash", status="voided", idx=6)
    await _seed_sale(client_id, user["id"], days_ago=40, total=999.0, items=[],
                     payment_method="card", idx=7)

    resp = await client.get(
        "/api/v1/assistant/query?q=how do my customers pay", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["intent"] == "payment_mix"
    data = body["data"]
    assert data["order_count"] == 3  # two card + one cash; refund not an order
    assert abs(data["total_net"] - 750.0) < 0.01  # 500 card + 250 cash

    methods = data["methods"]
    assert [m["method"] for m in methods] == ["card", "cash"]  # ranked by revenue
    card, cash = methods
    assert abs(card["net_sales"] - 500.0) < 0.01
    assert card["order_count"] == 2
    assert abs(card["share"] - (500.0 / 750.0)) < 0.001
    assert abs(cash["net_sales"] - 250.0) < 0.01
    assert cash["order_count"] == 1

    assert data["dominant"]["method"] == "card"
    assert "card" in body["answer"].lower()


async def test_assistant_payment_mix_handles_empty_window(client):
    """No sales in the window → graceful message, empty breakdown, HTTP 200."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    resp = await client.get(
        "/api/v1/assistant/query?q=what is my cash vs card breakdown", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["intent"] == "payment_mix"
    assert body["data"]["methods"] == []
    assert body["data"]["dominant"] is None
    assert body["data"]["order_count"] == 0


async def test_assistant_reports_vat_collected(client):
    """"How much VAT have I collected?" → net VAT over the last 30 days, grounded
    in the tenant's own ``vat_amount`` figures. Credit notes net their VAT back
    out (a refund returns the tax too); held/voided and out-of-window tickets
    never count. The effective rate is VAT ÷ the taxable base."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    # Two taxable sales: 115 total = 100 base + 15 VAT, and 230 = 200 + 30.
    await _seed_sale(client_id, user["id"], days_ago=2, total=115.0, items=[],
                     vat=15.0, idx=1)
    await _seed_sale(client_id, user["id"], days_ago=3, total=230.0, items=[],
                     vat=30.0, idx=2)
    # A credit note nets its VAT back out: -46 total, -6 VAT.
    await _seed_sale(client_id, user["id"], days_ago=4, total=46.0, items=[],
                     vat=6.0, status="credit_note", idx=3)
    # Held/voided and out-of-window tickets must never count.
    await _seed_sale(client_id, user["id"], days_ago=1, total=999.0, items=[],
                     vat=130.0, status="held", idx=4)
    await _seed_sale(client_id, user["id"], days_ago=1, total=999.0, items=[],
                     vat=130.0, status="voided", idx=5)
    await _seed_sale(client_id, user["id"], days_ago=40, total=999.0, items=[],
                     vat=130.0, idx=6)

    resp = await client.get(
        "/api/v1/assistant/query?q=how much VAT have I collected", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["intent"] == "vat_owed"
    data = body["data"]
    # 15 + 30 − 6 = 39 net VAT across two orders (the refund is not an order).
    assert abs(data["vat_collected"] - 39.0) < 0.01
    assert data["order_count"] == 2
    # Net takings 115 + 230 − 46 = 299; taxable base = 299 − 39 = 260.
    assert abs(data["net_sales"] - 299.0) < 0.01
    assert abs(data["taxable_base"] - 260.0) < 0.01
    assert abs(data["effective_rate"] - (39.0 / 260.0)) < 0.001
    assert "39" in body["answer"]


async def test_assistant_vat_handles_empty_window(client):
    """No sales in the window → graceful message, zeroed figures, HTTP 200."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    resp = await client.get(
        "/api/v1/assistant/query?q=how much tax do I owe", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["intent"] == "vat_owed"
    assert body["data"]["vat_collected"] == 0.0
    assert body["data"]["order_count"] == 0
    assert body["data"]["effective_rate"] == 0.0


# ---------------------------------------------------------------------------
# inventory_value — "how much is my stock worth?" (#228 — M9·AI)
# ---------------------------------------------------------------------------


async def test_assistant_values_on_hand_inventory(client):
    """"How much is my stock worth?" → on-hand valued at cost and at retail."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    # 10 @ cost 4 / price 10  +  5 @ cost 20 / price 30.
    await _seed_product(client_id, user["id"], name="Latte", quantity=10,
                        price=10.0, cost_price=4.0)
    await _seed_product(client_id, user["id"], name="Grinder", quantity=5,
                        price=30.0, cost_price=20.0)

    resp = await client.get(
        "/api/v1/assistant/query?q=how much is my inventory worth", headers=headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["intent"] == "inventory_value"
    data = body["data"]
    # cost: 10*4 + 5*20 = 140 ; retail: 10*10 + 5*30 = 250 ; margin: 110.
    assert data["cost_value"] == 140.0
    assert data["retail_value"] == 250.0
    assert data["potential_margin"] == 110.0
    assert data["sku_count"] == 2
    assert data["total_units"] == 15
    assert data["unpriced_count"] == 0
    assert "140" in body["answer"]


async def test_assistant_inventory_value_excludes_digital_and_inactive(client):
    """Digital goods carry no physical stock; archived products aren't on hand."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    await _seed_product(client_id, user["id"], name="Beans", quantity=10,
                        price=10.0, cost_price=4.0)
    # Digital voucher — excluded even though it has a "quantity" and price.
    await _seed_product(client_id, user["id"], name="Gift Card", quantity=100,
                        price=50.0, cost_price=50.0, is_digital=True)
    # Archived product — no longer on the shelf.
    await _seed_product(client_id, user["id"], name="Old Mug", quantity=7,
                        price=8.0, cost_price=3.0, is_active=False)

    resp = await client.get(
        "/api/v1/assistant/query?q=what is my stock value", headers=headers
    )
    body = resp.json()
    assert body["intent"] == "inventory_value"
    data = body["data"]
    # Only Beans counts: cost 40, retail 100.
    assert data["cost_value"] == 40.0
    assert data["retail_value"] == 100.0
    assert data["sku_count"] == 1
    assert data["total_units"] == 10


async def test_assistant_inventory_value_flags_products_without_cost(client):
    """A SKU with no cost price can't be valued at cost, but is counted/retailed."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    await _seed_product(client_id, user["id"], name="Latte", quantity=10,
                        price=10.0, cost_price=4.0)
    # No cost_price → excluded from cost_value, surfaced as unpriced.
    await _seed_product(client_id, user["id"], name="Mystery", quantity=5,
                        price=12.0, cost_price=None)

    resp = await client.get(
        "/api/v1/assistant/query?q=how much is my inventory worth", headers=headers
    )
    body = resp.json()
    data = body["data"]
    assert data["cost_value"] == 40.0            # only Latte has a cost
    assert data["retail_value"] == 160.0         # 10*10 + 5*12
    assert data["sku_count"] == 2
    assert data["unpriced_count"] == 1


async def test_assistant_inventory_value_empty_catalogue(client):
    """No stock → zeros and a graceful answer, never a crash."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    resp = await client.get(
        "/api/v1/assistant/query?q=how much is my inventory worth", headers=headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["intent"] == "inventory_value"
    data = body["data"]
    assert data["cost_value"] == 0.0
    assert data["retail_value"] == 0.0
    assert data["sku_count"] == 0


async def test_assistant_inventory_value_routes_in_arabic(client):
    """Arabic "قيمة المخزون" routes to inventory_value, not the low-stock list."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    await _seed_product(client_id, user["id"], name="Latte", quantity=10,
                        price=10.0, cost_price=4.0)

    resp = await client.get(
        "/api/v1/assistant/query?q=كم قيمة المخزون", headers=headers
    )
    body = resp.json()
    assert body["intent"] == "inventory_value"
    assert body["data"]["cost_value"] == 40.0


async def test_assistant_names_the_top_customer(client):
    """"Who are my best customers?" → the customer with the most net spend over
    30 days; a credit note nets against that customer, walk-in (unnamed) sales are
    excluded, and a sale outside the window doesn't count."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    # Maha spends 500 net (600 − 100 refund) across 2 counted orders; Sami 300.
    await _seed_sale(client_id, user["id"], days_ago=1, total=600.0, items=[],
                     idx=1, customer_name="Maha", customer_phone="0500000001")
    await _seed_sale(client_id, user["id"], days_ago=2, total=100.0, items=[],
                     status="credit_note", idx=2,
                     customer_name="Maha", customer_phone="0500000001")
    await _seed_sale(client_id, user["id"], days_ago=3, total=300.0, items=[],
                     idx=3, customer_name="Sami", customer_phone="0500000002")
    # A walk-in (no customer identity) must NOT surface as a customer.
    await _seed_sale(client_id, user["id"], days_ago=1, total=999.0, items=[], idx=4)
    # An old sale (outside the 30-day window) must NOT count.
    await _seed_sale(client_id, user["id"], days_ago=45, total=999.0, items=[],
                     idx=5, customer_name="Maha", customer_phone="0500000001")

    resp = await client.get(
        "/api/v1/assistant/query?q=who are my best customers", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["method"] == "rule_based"
    assert body["intent"] == "top_customer"
    data = body["data"]
    assert data["customer_count"] == 2
    top = data["top"]
    assert top["name"] == "Maha"
    assert abs(top["net_spent"] - 500.0) < 0.01
    assert top["order_count"] == 1          # the refund is not itself an order
    # Ranked: Maha (500) ahead of Sami (300).
    assert [c["name"] for c in data["customers"]] == ["Maha", "Sami"]
    assert "Maha" in body["answer"]


async def test_assistant_top_customer_handles_no_customers(client):
    """No identified customers → an empty ranking and a graceful answer, no crash."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    # Only walk-in sales exist — nobody to rank.
    await _seed_sale(client_id, user["id"], days_ago=1, total=100.0, items=[], idx=1)

    resp = await client.get(
        "/api/v1/assistant/query?q=who is my best customer", headers=headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["intent"] == "top_customer"
    data = body["data"]
    assert data["customer_count"] == 0
    assert data["top"] is None
    assert data["customers"] == []


async def test_assistant_top_customer_routes_in_arabic(client):
    """Arabic "أفضل عميل" routes to top_customer."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    await _seed_sale(client_id, user["id"], days_ago=1, total=250.0, items=[],
                     idx=1, customer_name="Layla", customer_phone="0500000009")

    resp = await client.get(
        "/api/v1/assistant/query?q=من هو أفضل عميل", headers=headers
    )
    body = resp.json()
    assert body["intent"] == "top_customer"
    assert body["data"]["top"]["name"] == "Layla"


# ---------------------------------------------------------------------------
# refunds — "how much did I refund?" (#228 — M9·AI)
# ---------------------------------------------------------------------------


async def test_assistant_reports_refunds(client):
    """"How much did I refund?" → total credit-note value over the last 30 days,
    the refund count, and the refund rate (refunds ÷ gross sales). Held/voided and
    out-of-window tickets never count; the answer names the refunded total."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    # Gross sales in window: 400 + 600 = 1000 across two orders.
    await _seed_sale(client_id, user["id"], days_ago=2, total=400.0, items=[], idx=1)
    await _seed_sale(client_id, user["id"], days_ago=3, total=600.0, items=[], idx=2)
    # Two refunds (credit notes): 50 + 100 = 150.
    await _seed_sale(client_id, user["id"], days_ago=4, total=50.0, items=[],
                     status="credit_note", idx=3)
    await _seed_sale(client_id, user["id"], days_ago=5, total=100.0, items=[],
                     status="credit_note", idx=4)
    # Held/voided and out-of-window tickets must never count.
    await _seed_sale(client_id, user["id"], days_ago=1, total=999.0, items=[],
                     status="held", idx=5)
    await _seed_sale(client_id, user["id"], days_ago=1, total=999.0, items=[],
                     status="voided", idx=6)
    await _seed_sale(client_id, user["id"], days_ago=40, total=999.0, items=[],
                     status="credit_note", idx=7)

    resp = await client.get(
        "/api/v1/assistant/query?q=how much did I refund", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["intent"] == "refunds"
    data = body["data"]
    assert abs(data["refund_total"] - 150.0) < 0.01
    assert data["refund_count"] == 2
    assert abs(data["gross_sales"] - 1000.0) < 0.01
    assert data["order_count"] == 2
    assert abs(data["refund_rate"] - 0.15) < 0.001  # 150 / 1000
    assert abs(data["avg_refund"] - 75.0) < 0.01
    assert "150" in body["answer"]


async def test_assistant_refunds_handles_no_refunds(client):
    """Sales but no refunds → zeroed refund figures and a graceful answer, HTTP 200."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    await _seed_sale(client_id, user["id"], days_ago=1, total=250.0, items=[], idx=1)

    resp = await client.get(
        "/api/v1/assistant/query?q=how much have I refunded", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["intent"] == "refunds"
    data = body["data"]
    assert data["refund_total"] == 0.0
    assert data["refund_count"] == 0
    assert data["refund_rate"] == 0.0
    assert data["avg_refund"] == 0.0


async def test_assistant_refunds_routes_in_arabic(client):
    """Arabic "المرتجعات" routes to the refunds intent (not swallowed by another)."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    await _seed_sale(client_id, user["id"], days_ago=1, total=80.0, items=[],
                     status="credit_note", idx=1)

    resp = await client.get(
        "/api/v1/assistant/query?q=كم قيمة المرتجعات هذا الشهر", headers=headers
    )
    body = resp.json()
    assert body["intent"] == "refunds"
    assert abs(body["data"]["refund_total"] - 80.0) < 0.01


# ---------------------------------------------------------------------------
# expenses — "how much did I spend on expenses?" (#228 — M9·AI)
# ---------------------------------------------------------------------------


async def test_assistant_reports_expenses(client):
    """"How much did I spend on expenses?" → total recorded outgoings over the last
    30 days, the expense count, the average, and the breakdown by category with the
    biggest cost centre named. Out-of-window expenses never count; the answer names
    the total and the top category."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    # In-window expenses: Rent 3000, Salaries 2000 + 1500, Utilities 500 → 7000.
    await _seed_expense(client_id, user["id"], days_ago=2, amount=3000.0,
                        category="Rent", idx=1)
    await _seed_expense(client_id, user["id"], days_ago=3, amount=2000.0,
                        category="Salaries", idx=2)
    await _seed_expense(client_id, user["id"], days_ago=4, amount=1500.0,
                        category="Salaries", idx=3)
    await _seed_expense(client_id, user["id"], days_ago=5, amount=500.0,
                        category="Utilities", idx=4)
    # An expense older than 30 days is out of window and must never count.
    await _seed_expense(client_id, user["id"], days_ago=40, amount=9999.0,
                        category="Rent", idx=5)

    resp = await client.get(
        "/api/v1/assistant/query?q=how much did I spend on expenses", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["intent"] == "expenses"
    data = body["data"]
    assert abs(data["expense_total"] - 7000.0) < 0.01
    assert data["expense_count"] == 4
    assert abs(data["avg_expense"] - 1750.0) < 0.01  # 7000 / 4
    assert data["lookback_days"] == 30
    # Categories ranked by spend: Salaries (3500) > Rent (3000) > Utilities (500).
    cats = data["categories"]
    assert [c["category"] for c in cats] == ["Salaries", "Rent", "Utilities"]
    assert abs(cats[0]["total"] - 3500.0) < 0.01
    assert cats[0]["count"] == 2
    assert data["top_category"]["category"] == "Salaries"
    assert "7000" in body["answer"]
    assert "Salaries" in body["answer"]


async def test_assistant_expenses_handles_no_expenses(client):
    """No expenses in the window → zeroed figures and a graceful answer, HTTP 200,
    never a divide-by-zero on the average."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    resp = await client.get(
        "/api/v1/assistant/query?q=what are my expenses", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["intent"] == "expenses"
    data = body["data"]
    assert data["expense_total"] == 0.0
    assert data["expense_count"] == 0
    assert data["avg_expense"] == 0.0
    assert data["categories"] == []
    assert data["top_category"] is None


async def test_assistant_expenses_routes_in_arabic(client):
    """Arabic "المصروفات" routes to the expenses intent, not another money read."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    await _seed_expense(client_id, user["id"], days_ago=1, amount=250.0,
                        category="Rent", idx=1)

    resp = await client.get(
        "/api/v1/assistant/query?q=كم المصروفات هذا الشهر", headers=headers
    )
    body = resp.json()
    assert body["intent"] == "expenses"
    assert abs(body["data"]["expense_total"] - 250.0) < 0.01


async def test_assistant_expenses_is_tenant_scoped(client):
    """One tenant's expenses never leak into another tenant's assistant."""
    user_a, token_a, client_a = await make_client_account(client)
    user_b, token_b, client_b = await make_client_account(client)

    # Tenant B has a big expense; tenant A has none.
    await _seed_expense(client_b, user_b["id"], days_ago=1, amount=5000.0,
                        category="Rent", idx=1)

    resp = await client.get(
        "/api/v1/assistant/query?q=how much did I spend on expenses",
        headers=auth_headers(token_a),
    )
    body = resp.json()
    assert body["intent"] == "expenses"
    assert body["data"]["expense_total"] == 0.0
    assert body["data"]["top_category"] is None


# ---------------------------------------------------------------------------
# net_profit — "am I making a profit?" (#228 — M9·AI)
# ---------------------------------------------------------------------------


async def test_assistant_reports_net_profit(client):
    """"What is my net profit?" → the bottom line over the last 30 days: net sales
    (gross takings minus refunds) minus recorded expenses. Held/voided and
    out-of-window tickets never count; refunds net gross takings down; the answer
    names the net profit figure and reads as a profit."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    # Gross takings: 600 + 400 = 1000 across two counted orders.
    await _seed_sale(client_id, user["id"], days_ago=2, total=600.0, items=[], idx=1)
    await _seed_sale(client_id, user["id"], days_ago=3, total=400.0, items=[], idx=2)
    # A refund (credit note) of 100 nets gross down → net sales 900.
    await _seed_sale(client_id, user["id"], days_ago=4, total=100.0, items=[],
                     status="credit_note", idx=3)
    # Held/voided are not selling activity; out-of-window is out of window.
    await _seed_sale(client_id, user["id"], days_ago=1, total=5000.0, items=[],
                     status="held", idx=4)
    await _seed_sale(client_id, user["id"], days_ago=1, total=7000.0, items=[],
                     status="voided", idx=5)
    await _seed_sale(client_id, user["id"], days_ago=40, total=9999.0, items=[], idx=6)

    # Expenses in window: Rent 300 + Salaries 200 = 500. Net profit = 900 − 500 = 400.
    await _seed_expense(client_id, user["id"], days_ago=2, amount=300.0,
                        category="Rent", idx=1)
    await _seed_expense(client_id, user["id"], days_ago=3, amount=200.0,
                        category="Salaries", idx=2)
    await _seed_expense(client_id, user["id"], days_ago=40, amount=9999.0,
                        category="Rent", idx=3)

    resp = await client.get(
        "/api/v1/assistant/query?q=what is my net profit", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["intent"] == "net_profit"
    data = body["data"]
    assert abs(data["gross_sales"] - 1000.0) < 0.01
    assert abs(data["refund_total"] - 100.0) < 0.01
    assert abs(data["net_sales"] - 900.0) < 0.01
    assert abs(data["expense_total"] - 500.0) < 0.01
    assert abs(data["net_profit"] - 400.0) < 0.01
    assert abs(data["profit_margin"] - round(400.0 / 900.0, 4)) < 0.0001
    assert data["is_profitable"] is True
    assert data["lookback_days"] == 30
    assert "400" in body["answer"]


async def test_assistant_net_profit_reads_as_a_loss(client):
    """When expenses outrun net sales the bottom line is negative and the answer
    reads as a loss, never a divide-by-zero or a stray positive figure."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    await _seed_sale(client_id, user["id"], days_ago=2, total=300.0, items=[], idx=1)
    await _seed_expense(client_id, user["id"], days_ago=2, amount=1000.0,
                        category="Rent", idx=1)

    resp = await client.get(
        "/api/v1/assistant/query?q=am I making money", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["intent"] == "net_profit"
    data = body["data"]
    assert abs(data["net_sales"] - 300.0) < 0.01
    assert abs(data["net_profit"] - (-700.0)) < 0.01
    assert data["is_profitable"] is False
    assert "loss" in body["answer"].lower()


async def test_assistant_net_profit_handles_no_activity(client):
    """No sales and no expenses → zeroed figures, break-even answer, HTTP 200,
    never a divide-by-zero on the margin."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    resp = await client.get(
        "/api/v1/assistant/query?q=what is my net profit", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["intent"] == "net_profit"
    data = body["data"]
    assert data["net_sales"] == 0.0
    assert data["expense_total"] == 0.0
    assert data["net_profit"] == 0.0
    assert data["profit_margin"] == 0.0
    assert data["is_profitable"] is False


async def test_assistant_net_profit_routes_in_arabic(client):
    """Arabic "صافي الربح" routes to net_profit, not swallowed by top_margin's bare
    "الربح" cue."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    await _seed_sale(client_id, user["id"], days_ago=1, total=500.0, items=[], idx=1)
    await _seed_expense(client_id, user["id"], days_ago=1, amount=200.0,
                        category="Rent", idx=1)

    resp = await client.get(
        "/api/v1/assistant/query?q=ما هو صافي الربح", headers=headers
    )
    body = resp.json()
    assert body["intent"] == "net_profit"
    assert abs(body["data"]["net_profit"] - 300.0) < 0.01


async def test_assistant_net_profit_does_not_steal_top_margin(client):
    """The "most profitable *product*" question must still route to top_margin — the
    net_profit cues are deliberately more specific than a bare "profitable"."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    resp = await client.get(
        "/api/v1/assistant/query?q=which product is most profitable", headers=headers
    )
    body = resp.json()
    assert body["intent"] == "top_margin"


async def test_assistant_net_profit_is_tenant_scoped(client):
    """One tenant's sales and expenses never leak into another's net-profit read."""
    user_a, token_a, client_a = await make_client_account(client)
    user_b, token_b, client_b = await make_client_account(client)

    # Tenant B has takings and expenses; tenant A has nothing.
    await _seed_sale(client_b, user_b["id"], days_ago=1, total=800.0, items=[], idx=1)
    await _seed_expense(client_b, user_b["id"], days_ago=1, amount=300.0,
                        category="Rent", idx=1)

    resp = await client.get(
        "/api/v1/assistant/query?q=am I profitable",
        headers=auth_headers(token_a),
    )
    body = resp.json()
    assert body["intent"] == "net_profit"
    assert body["data"]["net_sales"] == 0.0
    assert body["data"]["expense_total"] == 0.0
    assert body["data"]["net_profit"] == 0.0


async def test_assistant_reports_order_count(client):
    """"How many orders did I get?" → the count of completed orders over the last
    30 days (plus today's), grounded in the tenant's own transactions.

    Distinct from ``sales_today`` (which answers *how much money*): this answers
    *how many tickets*. A credit note is a refund, not a new order, so it never
    inflates the count; held/voided tickets are not selling activity; out-of-window
    sales are out of window. Today's orders are surfaced alongside the window total,
    and a daily average frames the volume."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    # Three completed orders today + one three days ago = 4 counted in the window.
    await _seed_sale(client_id, user["id"], days_ago=0, total=100.0, items=[], idx=1)
    await _seed_sale(client_id, user["id"], days_ago=0, total=200.0, items=[], idx=2)
    await _seed_sale(client_id, user["id"], days_ago=0, total=300.0, items=[], idx=3)
    await _seed_sale(client_id, user["id"], days_ago=3, total=400.0, items=[], idx=4)
    # A credit note is a refund, not a new order → never counted.
    await _seed_sale(client_id, user["id"], days_ago=1, total=50.0, items=[],
                     status="credit_note", idx=5)
    # Held/voided are not selling activity; out-of-window is out of window.
    await _seed_sale(client_id, user["id"], days_ago=1, total=10.0, items=[],
                     status="held", idx=6)
    await _seed_sale(client_id, user["id"], days_ago=1, total=10.0, items=[],
                     status="voided", idx=7)
    await _seed_sale(client_id, user["id"], days_ago=40, total=999.0, items=[], idx=8)

    resp = await client.get(
        "/api/v1/assistant/query?q=how many orders did I get", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["method"] == "rule_based"
    assert body["intent"] == "order_count"
    data = body["data"]
    assert data["order_count"] == 4
    assert data["orders_today"] == 3
    assert data["lookback_days"] == 30
    assert abs(data["daily_average"] - round(4 / 30, 1)) < 0.001
    assert "4" in body["answer"]


async def test_assistant_order_count_handles_no_orders(client):
    """No sales at all → a zeroed count, a break-even-style answer, and HTTP 200
    (never a divide-by-zero on the daily average)."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    resp = await client.get(
        "/api/v1/assistant/query?q=how many transactions did I have", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["intent"] == "order_count"
    data = body["data"]
    assert data["order_count"] == 0
    assert data["orders_today"] == 0
    assert data["daily_average"] == 0.0


async def test_assistant_order_count_routes_in_arabic(client):
    """Arabic "كم عدد الطلبات" (how many orders) routes to order_count, not swallowed
    by the smart_reorder or sales_today cues."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    await _seed_sale(client_id, user["id"], days_ago=1, total=100.0, items=[], idx=1)
    await _seed_sale(client_id, user["id"], days_ago=2, total=200.0, items=[], idx=2)

    resp = await client.get(
        "/api/v1/assistant/query?q=كم عدد الطلبات", headers=headers
    )
    body = resp.json()
    assert body["intent"] == "order_count"
    assert body["data"]["order_count"] == 2


async def test_assistant_order_count_does_not_steal_smart_reorder(client):
    """A "what should I reorder" question must still route to smart_reorder — the
    order_count cues are the vocabulary of *how many I sold*, not *what to order*."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    resp = await client.get(
        "/api/v1/assistant/query?q=what should I reorder", headers=headers
    )
    body = resp.json()
    assert body["intent"] == "smart_reorder"


async def test_assistant_order_count_is_tenant_scoped(client):
    """One tenant's orders never leak into another's order-count read."""
    user_a, token_a, client_a = await make_client_account(client)
    user_b, token_b, client_b = await make_client_account(client)

    await _seed_sale(client_b, user_b["id"], days_ago=1, total=100.0, items=[], idx=1)
    await _seed_sale(client_b, user_b["id"], days_ago=2, total=200.0, items=[], idx=2)

    resp = await client.get(
        "/api/v1/assistant/query?q=how many orders did I get",
        headers=auth_headers(token_a),
    )
    body = resp.json()
    assert body["intent"] == "order_count"
    assert body["data"]["order_count"] == 0


# ---------------------------------------------------------------------------
# discounts — "how much did I give away in discounts?" (#228 — M9·AI)
# ---------------------------------------------------------------------------


async def test_assistant_reports_discounts_given(client):
    """"How much did I give in discounts?" → total discount handed out at the till
    over the last 30 days, the number of discounted orders, the average discount,
    and the discount rate (discounts ÷ gross list price). Held/voided, credit notes
    and out-of-window tickets never count; the answer names the discounted total."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    # Discounted sales in window: 50 + 50 = 100 across two discounted orders.
    await _seed_sale(client_id, user["id"], days_ago=2, total=400.0, items=[],
                     discount=50.0, idx=1)
    await _seed_sale(client_id, user["id"], days_ago=3, total=350.0, items=[],
                     discount=50.0, idx=2)
    # A full-price sale counts as an order but carries no discount.
    await _seed_sale(client_id, user["id"], days_ago=4, total=200.0, items=[],
                     discount=0.0, idx=3)
    # Held/voided, credit notes and out-of-window discounts must never count.
    await _seed_sale(client_id, user["id"], days_ago=1, total=999.0, items=[],
                     discount=999.0, status="held", idx=4)
    await _seed_sale(client_id, user["id"], days_ago=1, total=999.0, items=[],
                     discount=999.0, status="voided", idx=5)
    await _seed_sale(client_id, user["id"], days_ago=1, total=999.0, items=[],
                     discount=999.0, status="credit_note", idx=6)
    await _seed_sale(client_id, user["id"], days_ago=40, total=999.0, items=[],
                     discount=999.0, idx=7)

    resp = await client.get(
        "/api/v1/assistant/query?q=how much did I give in discounts", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["intent"] == "discounts"
    data = body["data"]
    assert abs(data["discount_total"] - 100.0) < 0.01
    assert data["discounted_count"] == 2
    assert data["order_count"] == 3          # two discounted + one full-price
    assert abs(data["avg_discount"] - 50.0) < 0.01  # 100 / 2
    assert data["lookback_days"] == 30
    # Gross list = charged (400+350+200) + discounts (100) = 1050; rate = 100/1050.
    assert abs(data["discount_rate"] - round(100.0 / 1050.0, 4)) < 0.001
    assert "100" in body["answer"]


async def test_assistant_discounts_handles_none_given(client):
    """Sales but no discounts → zeroed discount figures and a graceful answer,
    HTTP 200, never a divide-by-zero on the average or the rate."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    await _seed_sale(client_id, user["id"], days_ago=1, total=250.0, items=[],
                     discount=0.0, idx=1)

    resp = await client.get(
        "/api/v1/assistant/query?q=how much have I discounted", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["intent"] == "discounts"
    data = body["data"]
    assert data["discount_total"] == 0.0
    assert data["discounted_count"] == 0
    assert data["discount_rate"] == 0.0
    assert data["avg_discount"] == 0.0


async def test_assistant_discounts_do_not_collide_with_markdown_suggestions(client):
    """The forward-looking "what should I discount?" still routes to dynamic_pricing;
    only history-shaped phrasings ("how much did I discount") route to discounts."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    resp = await client.get(
        "/api/v1/assistant/query?q=what should I discount", headers=headers
    )
    assert resp.json()["intent"] == "dynamic_pricing"


async def test_assistant_discounts_routes_in_arabic(client):
    """Arabic "الخصومات" routes to the discounts intent (not swallowed by another)."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    await _seed_sale(client_id, user["id"], days_ago=1, total=180.0, items=[],
                     discount=20.0, idx=1)

    resp = await client.get(
        "/api/v1/assistant/query?q=كم قيمة الخصومات هذا الشهر", headers=headers
    )
    body = resp.json()
    assert body["intent"] == "discounts"
    assert abs(body["data"]["discount_total"] - 20.0) < 0.01
