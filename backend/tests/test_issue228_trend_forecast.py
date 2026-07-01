"""Issue #228 (M9·AI) — sales-forecast *trend* model slice.

The first sales-forecast slice projected a **flat moving average** (mean daily
take, projected unchanged across the horizon). That is honest but blind to
direction: a shop whose takings are climbing week over week gets the same flat
line as one that is sinking. This slice adds a second, self-describing model to
the same ``/api/v1/reports/sales-forecast`` endpoint, selected with
``?method=linear_trend``:

* it splits the lookback window into an older half and a recent half (two
  server-side ``SUM``s — OPS-05, never O(transactions)), measures the change in
  average daily take between the two halves, and projects that slope forward, so
  a rising business forecasts a rising line and a falling one a falling line;
* it degrades gracefully — empty history forecasts a flat zero (no
  divide-by-zero / 500), and an unknown ``method`` is a clean 400, not a 500;
* the original ``moving_average`` model remains the default, unchanged, so the
  existing surface keeps working.

The split is a pure datetime comparison (not calendar-day bucketing), so the
projection is deterministic regardless of the wall clock.
"""
from datetime import datetime, timezone, timedelta

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
                    invoice_number=f"INV-TR-{client_id}-{i}",
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


async def test_linear_trend_projects_a_rising_line_above_the_flat_average(client):
    """A window whose recent half out-sells its older half forecasts upward.

    lookback=8 → two 4-day halves. Older half (days 4..7) takes 100/day; recent
    half (days 0..3) takes 200/day. The average daily take climbs by 100 across a
    4-day gap between the halves' centres → +25/day of trend. The recent-half
    average (200) sits ~2 days (lookback/4) after its centre from *now*, so:
        forecast(offset) = 200 + 25 * (2 + offset)
    """
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    specs = [(0, 200.0), (1, 200.0), (2, 200.0), (3, 200.0),   # recent half
             (4, 100.0), (5, 100.0), (6, 100.0), (7, 100.0)]   # older half
    await _seed_transactions(client_id, user["id"], specs)

    resp = await client.get(
        "/api/v1/reports/sales-forecast?lookback=8&horizon=2&method=linear_trend",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["method"] == "linear_trend"
    # +100 average-daily change over a 4-day centre gap → +25/day slope.
    assert abs(body["trend_per_day"] - 25.0) < 0.01
    # The flat moving average would be 1200/8 = 150; the trend must beat it.
    assert abs(body["avg_daily_sales"] - 150.0) < 0.01

    points = body["points"]
    assert len(points) == 2
    today = datetime.now(timezone.utc).date()
    for offset, pt in enumerate(points, start=1):
        expected = 200.0 + 25.0 * (2 + offset)
        assert abs(pt["forecast_sales"] - expected) < 0.01, (offset, pt)
        assert pt["date"] == (today + timedelta(days=offset)).strftime("%Y-%m-%d")
        # Every projected day out-runs the flat moving average — the point of it.
        assert pt["forecast_sales"] > 150.0


async def test_moving_average_remains_the_default_model(client):
    """Omitting ``method`` keeps the original flat forecast, unchanged."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    specs = [(0, 200.0), (1, 200.0), (2, 200.0), (3, 200.0),
             (4, 100.0), (5, 100.0), (6, 100.0), (7, 100.0)]
    await _seed_transactions(client_id, user["id"], specs)

    resp = await client.get(
        "/api/v1/reports/sales-forecast?lookback=8&horizon=2", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["method"] == "moving_average"
    # Flat mean = 1200/8 = 150, projected unchanged, with no trend tilt.
    assert abs(body["avg_daily_sales"] - 150.0) < 0.01
    assert abs(body["trend_per_day"]) < 0.01
    assert all(abs(p["forecast_sales"] - 150.0) < 0.01 for p in body["points"])


async def test_linear_trend_empty_history_is_flat_zero(client):
    """No sales in the window → a flat zero forecast, not a divide-by-zero / 500."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    resp = await client.get(
        "/api/v1/reports/sales-forecast?lookback=30&horizon=5&method=linear_trend",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["method"] == "linear_trend"
    assert abs(body["trend_per_day"]) < 0.01
    assert len(body["points"]) == 5
    assert all(abs(p["forecast_sales"]) < 0.01 for p in body["points"])


async def test_unknown_method_is_a_clean_400(client):
    """An unsupported model is rejected explicitly, not silently or with a 500."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    resp = await client.get(
        "/api/v1/reports/sales-forecast?method=quantum_oracle", headers=headers
    )
    assert resp.status_code == 400, resp.text


async def test_linear_trend_falling_business_forecasts_downward(client):
    """A window whose recent half under-sells its older half forecasts downward,
    and the projection is floored at zero rather than going negative."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    # Mirror of the rising case: older half strong (200/day), recent half weak
    # (20/day) → a steep negative slope that would drive the line below zero.
    specs = [(0, 20.0), (1, 20.0), (2, 20.0), (3, 20.0),
             (4, 200.0), (5, 200.0), (6, 200.0), (7, 200.0)]
    await _seed_transactions(client_id, user["id"], specs)

    resp = await client.get(
        "/api/v1/reports/sales-forecast?lookback=8&horizon=6&method=linear_trend",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["trend_per_day"] < 0  # sales are trending down
    forecasts = [p["forecast_sales"] for p in body["points"]]
    assert all(f >= 0.0 for f in forecasts)  # never negative revenue
    # A falling line: no point exceeds the one before it.
    assert all(b <= a + 0.01 for a, b in zip(forecasts, forecasts[1:]))
