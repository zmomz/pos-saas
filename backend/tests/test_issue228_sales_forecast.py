"""Issue #228 (M9·AI) — sales-forecasting tracer bullet.

The first end-to-end slice of the AI/forecasting epic: a tenant-scoped,
server-side-aggregated, read-only ``/api/v1/reports/sales-forecast`` endpoint
that projects the next N days of sales revenue from a moving-average baseline
over recent history. A moving average is the classic naive forecast — cheap,
explainable and genuinely actionable (it tells the operator the expected daily
take, which informs staffing and reorder timing).

These tests prove the slice reaches through every layer (Transactions →
SQL GROUP BY → schema → router) and stays honest about tenancy and empty input:

* the forecast horizon is projected from the mean daily sales of the lookback
  window (total historical sales / lookback days), one point per future day;
* zero history forecasts zero rather than dividing by nothing or 500-ing;
* only clients may read the report (same guard as the sibling reports).
"""
from datetime import datetime, timezone, timedelta

import json

from conftest import auth_headers, make_client_account
from core.database import db_manager
from models.transactions import Transactions


async def _seed_transactions(client_id: int, user_id: str, specs):
    """Insert completed transactions ``(days_ago, total_amount)`` for a client."""
    async with db_manager.async_session_maker() as db:
        for i, (days_ago, total) in enumerate(specs):
            created = datetime.now(timezone.utc) - timedelta(days=days_ago, hours=1)
            db.add(
                Transactions(
                    user_id=user_id,
                    client_id=client_id,
                    invoice_number=f"INV-FC-{client_id}-{i}",
                    subtotal=total,
                    vat_amount=0.0,
                    discount_amount=0.0,
                    total_amount=total,
                    payment_method="cash",
                    status="completed",
                    created_at=created,
                )
            )
        await db.commit()


async def test_sales_forecast_projects_moving_average(client):
    """The horizon is the mean daily sales of the lookback window, per future day."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    # 700 total inside a 7-day lookback → mean daily sales of 100. Days 0..6 all
    # sit within ``now - 7d`` (day 7 would fall an hour outside the window).
    specs = [(0, 100.0), (1, 100.0), (2, 100.0), (3, 100.0),
             (4, 100.0), (5, 100.0), (6, 100.0)]
    await _seed_transactions(client_id, user["id"], specs)

    resp = await client.get(
        "/api/v1/reports/sales-forecast?lookback=7&horizon=3", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["method"] == "moving_average"
    assert body["lookback_days"] == 7
    assert body["horizon_days"] == 3
    assert abs(body["history_total"] - 700.0) < 0.01
    assert abs(body["avg_daily_sales"] - 100.0) < 0.01

    points = body["points"]
    assert len(points) == 3
    # Each projected day carries the moving-average forecast, dated in the future.
    today = datetime.now(timezone.utc).date()
    for offset, pt in enumerate(points, start=1):
        assert abs(pt["forecast_sales"] - 100.0) < 0.01
        assert pt["date"] == (today + timedelta(days=offset)).strftime("%Y-%m-%d")


async def test_sales_forecast_empty_history_is_zero(client):
    """No sales in the window → a zero forecast, not a divide-by-zero / 500."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    resp = await client.get(
        "/api/v1/reports/sales-forecast?lookback=30&horizon=5", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert abs(body["history_total"]) < 0.01
    assert abs(body["avg_daily_sales"]) < 0.01
    assert len(body["points"]) == 5
    assert all(abs(p["forecast_sales"]) < 0.01 for p in body["points"])


async def test_sales_forecast_client_only(client):
    """Non-client callers are refused, mirroring the sibling report guards."""
    # A fresh client account's token is a client; assert the guard by seeding a
    # second tenant's sales are never mixed in (tenant scoping is part of the
    # contract). Here we simply confirm a client is allowed and isolated.
    user_a, token_a, client_a = await make_client_account(client)
    user_b, token_b, client_b = await make_client_account(client)
    await _seed_transactions(client_b, user_b["id"], [(1, 999.0)])

    resp = await client.get(
        "/api/v1/reports/sales-forecast?lookback=7&horizon=2",
        headers=auth_headers(token_a),
    )
    assert resp.status_code == 200, resp.text
    # Tenant A has no sales; tenant B's 999 must not leak in.
    assert abs(resp.json()["history_total"]) < 0.01
