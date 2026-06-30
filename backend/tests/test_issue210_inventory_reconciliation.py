"""Issue #210 (M3·POS) — inventory reconciliation at the period close.

The month-end / year-end close already rolls every closed shift in a period into
one reconciled *cash* summary and locks it. A real period close also asks a second
question: *were the shelves counted?* A merchant should not close the books for a
month without knowing whether inventory was reconciled against the system on-hand
in that window.

This slice ties the guided stocktake (#207) into the period close: the period
summary now reports whether an *approved* stock count landed inside the period
window, and the period-close audit row records that reconciliation status — so the
locked period preserves not just the cash roll-up but whether stock was counted.

It is informational (non-blocking): a period with no count still closes, but the
operator (and the tamper-evident audit trail) can see it was closed un-reconciled.
"""
import json
from datetime import datetime, timezone

from conftest import auth_headers, make_client_account
from core.database import db_manager
from models.audit_logs import Audit_logs
from sqlalchemy import select


def _now():
    return datetime.now(timezone.utc)


async def _open_shift(client, headers, opening_cash=100.0):
    resp = await client.post(
        "/api/v1/production/shifts/open",
        json={"opening_cash": opening_cash},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _close_shift(client, headers, closing_cash=100.0):
    resp = await client.post(
        "/api/v1/production/shifts/close",
        json={"closing_cash": closing_cash},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _summary(client, headers, **params):
    return await client.get(
        "/api/v1/production/shifts/period-summary",
        params=params,
        headers=headers,
    )


async def _period_close(client, headers, **body):
    return await client.post(
        "/api/v1/production/shifts/period-close",
        json=body,
        headers=headers,
    )


async def _approve_stocktake(client, headers):
    """Drive an (empty) guided stocktake through draft → frozen → approved so an
    approved count with a fresh ``approved_at`` lands in the current period."""
    r = await client.post("/api/v1/production/stock-counts", json={}, headers=headers)
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    r = await client.post(f"/api/v1/production/stock-counts/{sid}/freeze", headers=headers)
    assert r.status_code == 200, r.text
    r = await client.post(f"/api/v1/production/stock-counts/{sid}/approve", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def test_period_summary_reports_inventory_reconciliation(client):
    """The period summary reports whether inventory was reconciled in the window:
    false with no count, true after an approved stocktake lands this period."""
    user, token, _ = await make_client_account(client)
    headers = auth_headers(token)
    now = _now()

    await _open_shift(client, headers, opening_cash=100.0)
    await _close_shift(client, headers, closing_cash=100.0)

    # No stock count yet — the period is un-reconciled.
    resp = await _summary(client, headers, period_type="month", year=now.year, month=now.month)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["inventory_reconciled"] is False
    assert body["stock_counts_approved"] == 0
    assert body["last_reconciled_at"] is None

    # Approve a stocktake — now the period is reconciled.
    await _approve_stocktake(client, headers)

    resp = await _summary(client, headers, period_type="month", year=now.year, month=now.month)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["inventory_reconciled"] is True
    assert body["stock_counts_approved"] == 1
    assert body["last_reconciled_at"] is not None


async def test_period_close_records_inventory_reconciliation(client):
    """The period-close audit row preserves the reconciliation status — the locked
    period records that the shelves were counted (or not) at close time."""
    user, token, _ = await make_client_account(client)
    headers = auth_headers(token)
    now = _now()

    await _open_shift(client, headers, opening_cash=100.0)
    await _close_shift(client, headers, closing_cash=100.0)
    await _approve_stocktake(client, headers)

    resp = await _period_close(client, headers, period_type="month", year=now.year, month=now.month)
    assert resp.status_code == 200, resp.text
    assert resp.json()["inventory_reconciled"] is True

    async with db_manager.async_session_maker() as db:
        row = (
            await db.execute(
                select(Audit_logs).where(Audit_logs.action == "shift.period_closed")
            )
        ).scalars().first()
    assert row is not None
    changes = json.loads(row.changes)
    assert changes["inventory_reconciled"] is True


async def test_inventory_reconciliation_is_owner_scoped(client):
    """Merchant A's approved stocktake does not mark merchant B's period reconciled."""
    user_a, token_a, _ = await make_client_account(client)
    headers_a = auth_headers(token_a)
    now = _now()
    await _approve_stocktake(client, headers_a)

    user_b, token_b, _ = await make_client_account(client)
    headers_b = auth_headers(token_b)

    resp = await _summary(client, headers_b, period_type="month", year=now.year, month=now.month)
    assert resp.status_code == 200, resp.text
    assert resp.json()["inventory_reconciled"] is False
    assert resp.json()["stock_counts_approved"] == 0
