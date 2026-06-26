"""FIN-07 — advance the billing period from the current period end, not ``now``.

An early renewal (the merchant pays while the current paid period still has unused
days left) used to advance ``next_billing_date`` to ``now + cycle``, silently
forfeiting the remaining paid time and walking the billing day forward every time.
The fix anchors the new period to the *current* period end (``next_billing_date``)
when it is still in the future, so the unused remainder is kept and the billing day
stays fixed. An on-time renewal is unchanged; an overdue charge still starts from
now.

The pure ``advance_billing_period`` helper is the testable core; the pay endpoint
wires it end-to-end.
"""
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, func, select, update

from conftest import auth_headers, make_agent_account, make_client_under_agent
from core.database import db_manager
from models.agent_quota_payments import Agent_quota_payments
from models.agents import Agents
from models.clients import Clients
from models.subscription_payments import Subscription_payments


@pytest.fixture(autouse=True)
async def _purge_payments_created_here():
    """The shared test DB has no per-test isolation (TST-04/#172), so the settled
    payments these tests record must not leak into the platform-wide revenue
    rollups other suites assert on. Delete only rows inserted here (id beyond the
    pre-test high-water mark) on the way out (mirrors test_fin04)."""
    async with db_manager.async_session_maker() as db:
        sub_max = (await db.execute(select(func.max(Subscription_payments.id)))).scalar() or 0
        quota_max = (await db.execute(select(func.max(Agent_quota_payments.id)))).scalar() or 0
    yield
    async with db_manager.async_session_maker() as db:
        await db.execute(delete(Subscription_payments).where(Subscription_payments.id > sub_max))
        await db.execute(delete(Agent_quota_payments).where(Agent_quota_payments.id > quota_max))
        await db.commit()


# ---------------------------------------------------------------------------
# Pure core: anchor the next period end to the current one when still in future.
# ---------------------------------------------------------------------------
def test_early_renewal_keeps_remaining_paid_time():
    from core.billing_period import advance_billing_period

    # Paid period still runs to Jan 20; the merchant renews early on Jan 10.
    now = datetime(2026, 1, 10, tzinfo=timezone.utc)
    # The new period anchors to Jan 20 (not Jan 10), so the 10 unused days are
    # kept: Jan 20 + 30 days = Feb 19.
    assert advance_billing_period(now, "2026-01-20", "monthly") == "2026-02-19"


def test_on_time_renewal_is_unchanged():
    from core.billing_period import advance_billing_period

    # Renewing exactly on the billing day: the period end is today (not in the
    # future), so the anchor is today and the result equals plain now + cycle.
    now = datetime(2026, 1, 20, tzinfo=timezone.utc)
    assert advance_billing_period(now, "2026-01-20", "monthly") == "2026-02-19"


def test_overdue_or_missing_advances_from_now():
    from core.billing_period import advance_billing_period

    now = datetime(2026, 1, 25, tzinfo=timezone.utc)
    # Overdue: the period end (Jan 20) is in the past, so it cannot be the anchor —
    # the new period starts from now, Jan 25 + 30 days = Feb 24.
    assert advance_billing_period(now, "2026-01-20", "monthly") == "2026-02-24"
    # No current period end at all -> from now, same result.
    assert advance_billing_period(now, None, "monthly") == "2026-02-24"
    # An unparseable date is treated as missing -> from now.
    assert advance_billing_period(now, "not-a-date", "monthly") == "2026-02-24"


def test_yearly_cycle_uses_365_days():
    from core.billing_period import advance_billing_period

    now = datetime(2026, 1, 10, tzinfo=timezone.utc)
    # Early yearly renewal anchors to the future period end + 365 days.
    assert advance_billing_period(now, "2026-01-20", "yearly") == "2027-01-20"


# ---------------------------------------------------------------------------
# End-to-end: an early manual renewal keeps the unused paid time (AC1).
# ---------------------------------------------------------------------------
async def _pin_period_end(client_id: int, next_billing_date: str):
    """Pin the client's current period end + a payable subscription fee."""
    async with db_manager.async_session_maker() as db:
        await db.execute(
            update(Clients)
            .where(Clients.id == client_id)
            .values(
                subscription_fee=200.0,
                billing_cycle="monthly",
                subscription_status="active",
                next_billing_date=next_billing_date,
            )
        )
        await db.commit()


@pytest.mark.asyncio
async def test_early_pay_anchors_next_billing_date_to_current_period_end(client: AsyncClient):
    from datetime import timedelta

    _agent, _agent_token, agent_id = await make_agent_account(client)
    _cl, client_token, client_id = await make_client_under_agent(client, agent_id)

    # The current paid period still has 10 days left.
    today = datetime.now(timezone.utc).date()
    period_end = (today + timedelta(days=10)).isoformat()
    await _pin_period_end(client_id, period_end)

    pay = await client.post(
        "/api/v1/tenant/client/subscription/pay", headers=auth_headers(client_token)
    )
    assert pay.status_code == 200, pay.text
    body = pay.json()

    # The new period anchors to the existing period end (today+10), not to today,
    # so the 10 unused days are kept: next billing is today+10+30 = today+40, NOT
    # today+30 (the pre-FIN-07 forfeit-the-remainder behaviour).
    expected = (today + timedelta(days=40)).isoformat()
    assert body["next_billing_date"] == expected
    assert body["payments"][0]["period_end"] == expected
