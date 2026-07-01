"""Issue #229 (M9·Analytics) — peak-hours heatmap slice.

The advanced-analytics epic's CLV/repeat-rate slice answered "who are our
customers and what are they worth". This slice answers "*when* do we sell" — it
buckets the tenant's completed sales into a day-of-week × hour-of-day grid, the
raw material for a peak-hours heatmap that tells a merchant when to staff up.

Like the sibling customer-analytics report it groups server-side, stays honest
about tenancy, and excludes non-sale rows (held/voided tickets and credit-note
refunds are not selling activity). Behaviours proven end-to-end:

* sales land in the correct (day_of_week, hour) cell with count + revenue, and
  ``busiest`` names the hottest cell;
* held/voided/credit-note rows never enter the heatmap;
* an empty window yields no cells, no busiest, zero totals;
* one tenant's sales never leak into another tenant's heatmap.
"""
from datetime import datetime, timezone, timedelta

from conftest import auth_headers, make_client_account
from core.database import db_manager
from models.transactions import Transactions


async def _seed_sale(client_id, user_id, created_at, total, *, status="completed", idx=0):
    """One transaction stamped at an explicit ``created_at`` (UTC)."""
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
                created_at=created_at,
            )
        )
        await db.commit()


def _dow(dt):
    """0=Sunday .. 6=Saturday — matches Postgres extract('dow') and SQLite %w."""
    return int(dt.strftime("%w"))


async def test_sales_bucketed_by_day_and_hour_with_busiest(client):
    """Three sales share one cell, one sits in another; busiest is the trio's."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    # A "hot" cell: three sales two days ago at 09:00 (10 + 20 + 30 = 60).
    hot = (datetime.now(timezone.utc) - timedelta(days=2)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    await _seed_sale(client_id, user["id"], hot, 10.0, idx=0)
    await _seed_sale(client_id, user["id"], hot, 20.0, idx=1)
    await _seed_sale(client_id, user["id"], hot, 30.0, idx=2)
    # A quieter cell: one sale three days ago at 14:00.
    cool = (datetime.now(timezone.utc) - timedelta(days=3)).replace(
        hour=14, minute=0, second=0, microsecond=0
    )
    await _seed_sale(client_id, user["id"], cool, 5.0, idx=3)

    resp = await client.get("/api/v1/reports/peak-hours?lookback=30", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["method"] == "sales_heatmap"
    assert body["lookback_days"] == 30
    assert body["total_orders"] == 4
    assert abs(body["total_revenue"] - 65.0) < 0.001

    cells = {(c["day_of_week"], c["hour"]): c for c in body["cells"]}
    hot_cell = cells[(_dow(hot), 9)]
    assert hot_cell["order_count"] == 3
    assert abs(hot_cell["revenue"] - 60.0) < 0.001

    cool_cell = cells[(_dow(cool), 14)]
    assert cool_cell["order_count"] == 1
    assert abs(cool_cell["revenue"] - 5.0) < 0.001

    assert body["busiest"]["day_of_week"] == _dow(hot)
    assert body["busiest"]["hour"] == 9
    assert body["busiest"]["order_count"] == 3


async def test_held_voided_and_credit_notes_excluded(client):
    """Only completed sales are selling activity; refunds/parked tickets are not."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    when = (datetime.now(timezone.utc) - timedelta(days=1)).replace(
        hour=11, minute=0, second=0, microsecond=0
    )
    await _seed_sale(client_id, user["id"], when, 10.0, idx=0)  # counts
    await _seed_sale(client_id, user["id"], when, 99.0, status="held", idx=1)
    await _seed_sale(client_id, user["id"], when, 99.0, status="voided", idx=2)
    await _seed_sale(client_id, user["id"], when, 99.0, status="credit_note", idx=3)

    resp = await client.get("/api/v1/reports/peak-hours?lookback=30", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["total_orders"] == 1
    assert abs(body["total_revenue"] - 10.0) < 0.001
    assert len(body["cells"]) == 1
    cell = body["cells"][0]
    assert cell["day_of_week"] == _dow(when)
    assert cell["hour"] == 11
    assert cell["order_count"] == 1


async def test_empty_window_yields_no_cells(client):
    """No sales → empty grid, no busiest, zero totals (no crash)."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    resp = await client.get("/api/v1/reports/peak-hours?lookback=30", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["total_orders"] == 0
    assert body["total_revenue"] == 0.0
    assert body["cells"] == []
    assert body["busiest"] is None


async def test_peak_hours_is_tenant_scoped(client):
    """One tenant's sales never appear in another tenant's heatmap."""
    user_a, token_a, client_a = await make_client_account(client)
    user_b, token_b, client_b = await make_client_account(client)

    when = (datetime.now(timezone.utc) - timedelta(days=1)).replace(
        hour=8, minute=0, second=0, microsecond=0
    )
    await _seed_sale(client_b, user_b["id"], when, 500.0, idx=0)

    resp = await client.get(
        "/api/v1/reports/peak-hours?lookback=30", headers=auth_headers(token_a)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_orders"] == 0
    assert body["cells"] == []
    assert body["busiest"] is None
