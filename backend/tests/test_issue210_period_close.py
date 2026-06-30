"""Issue #210 (M3·POS) — month-end / year-end period close.

The shift lifecycle closes a *single drawer*; a merchant also needs to close a
*period* — roll every closed shift in a calendar month (or year) into one
reconciled summary and lock it, so the books for that period can't drift after
the fact. This slice adds:

* ``GET  /production/shifts/period-summary`` — a read-only roll-up of the closed
  shifts in a period (the preview the operator reviews before closing), plus
  whether the period is already closed and whether a drawer is still open;
* ``POST /production/shifts/period-close`` — runs the close: it aggregates the
  period, records it in the tamper-evident audit trail (``shift.period_closed``),
  and locks the period so a second close is refused.

Guards: a period can't be closed while a drawer is still open (close the
operational shift first), a future period can't be closed, and the aggregation is
owner-scoped.
"""
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


async def test_period_summary_aggregates_closed_shifts(client):
    """Two shifts opened and closed this month roll up into one summary: the
    count and the summed cash/sales totals, with nothing parked open."""
    user, token, _ = await make_client_account(client)
    headers = auth_headers(token)
    now = _now()

    await _open_shift(client, headers, opening_cash=100.0)
    await _close_shift(client, headers, closing_cash=105.0)
    await _open_shift(client, headers, opening_cash=50.0)
    await _close_shift(client, headers, closing_cash=50.0)

    resp = await _summary(client, headers, period_type="month", year=now.year, month=now.month)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["shifts_count"] == 2
    assert body["opening_cash"] == 150.0
    assert body["closing_cash"] == 155.0
    assert body["has_open_shift"] is False
    assert body["already_closed"] is False
    assert body["period_key"] == f"{now.year:04d}-{now.month:02d}"


async def test_period_close_records_audit_and_locks_the_period(client):
    """Closing the period records a tamper-evident audit row and locks it — a
    second close of the same period is refused."""
    user, token, _ = await make_client_account(client)
    headers = auth_headers(token)
    now = _now()

    await _open_shift(client, headers, opening_cash=100.0)
    await _close_shift(client, headers, closing_cash=100.0)

    resp = await _period_close(client, headers, period_type="month", year=now.year, month=now.month)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["shifts_count"] == 1
    assert body["closed_at"]

    async with db_manager.async_session_maker() as db:
        rows = (
            await db.execute(
                select(Audit_logs).where(Audit_logs.action == "shift.period_closed")
            )
        ).scalars().all()
    assert len(rows) == 1
    assert rows[0].entity_type == "period"
    assert rows[0].entity_id == f"{now.year:04d}-{now.month:02d}"

    # A second close of the same period is refused — the period is locked.
    again = await _period_close(client, headers, period_type="month", year=now.year, month=now.month)
    assert again.status_code == 400
    assert "already" in again.json()["detail"].lower()


async def test_cannot_close_period_while_a_shift_is_open(client):
    """A drawer still open means operational work is unfinished — the period can't
    be closed until it is closed first."""
    user, token, _ = await make_client_account(client)
    headers = auth_headers(token)
    now = _now()

    await _open_shift(client, headers, opening_cash=100.0)  # left open

    resp = await _period_close(client, headers, period_type="month", year=now.year, month=now.month)
    assert resp.status_code == 400
    assert "open" in resp.json()["detail"].lower()


async def test_cannot_close_a_future_period(client):
    """A period that has not started yet cannot be closed."""
    user, token, _ = await make_client_account(client)
    headers = auth_headers(token)
    now = _now()

    resp = await _period_close(client, headers, period_type="year", year=now.year + 1)
    assert resp.status_code == 400
    assert "future" in resp.json()["detail"].lower()


async def test_period_close_is_owner_scoped(client):
    """The roll-up only sees the caller's own shifts — merchant B's period summary
    does not include merchant A's closed shift."""
    user_a, token_a, _ = await make_client_account(client)
    headers_a = auth_headers(token_a)
    now = _now()
    await _open_shift(client, headers_a, opening_cash=100.0)
    await _close_shift(client, headers_a, closing_cash=100.0)

    user_b, token_b, _ = await make_client_account(client)
    headers_b = auth_headers(token_b)

    resp = await _summary(client, headers_b, period_type="month", year=now.year, month=now.month)
    assert resp.status_code == 200, resp.text
    assert resp.json()["shifts_count"] == 0


async def test_month_period_requires_a_valid_month(client):
    """A month close without a valid month is rejected."""
    user, token, _ = await make_client_account(client)
    headers = auth_headers(token)
    now = _now()

    resp = await _period_close(client, headers, period_type="month", year=now.year, month=13)
    assert resp.status_code == 400
    assert "month" in resp.json()["detail"].lower()
