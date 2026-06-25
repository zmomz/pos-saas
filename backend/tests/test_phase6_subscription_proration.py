"""Phase 6 — proration on mid-cycle plan changes (ISSUE-053, F-053 billing).

Changing a client's subscription_fee partway through a paid billing period bills
(or credits) the pro-rated difference for the unused remainder of the cycle; the
next full invoice then bills the new fee in full. The pure ``compute_proration``
helper is the testable core; the agent set endpoint wires it end-to-end.
"""
# ---------------------------------------------------------------------------
# Pure core: the proration math (charge on upgrade, credit on downgrade).
# ---------------------------------------------------------------------------
def test_compute_proration_charges_and_credits_the_unused_remainder():
    from services.subscription_billing import compute_proration

    # Upgrade 200 -> 300 with half the monthly cycle left -> +50 charge.
    assert compute_proration(200.0, 300.0, 15, 30) == 50.0
    # Downgrade 300 -> 100 with half the cycle left -> -100 credit.
    assert compute_proration(300.0, 100.0, 15, 30) == -100.0
    # A full cycle remaining bills the whole difference.
    assert compute_proration(200.0, 300.0, 30, 30) == 100.0
    # No remaining days (period already elapsed) -> no proration.
    assert compute_proration(200.0, 300.0, 0, 30) == 0.0
    # Days beyond the cycle length are clamped to a full cycle (never > 1x).
    assert compute_proration(200.0, 300.0, 45, 30) == 100.0


# ---------------------------------------------------------------------------
# End-to-end: an agent raises the fee mid-cycle -> a prorated charge is recorded
# for the unused remainder, and the next full payment bills the new fee (AC1/AC2).
# ---------------------------------------------------------------------------
import pytest  # noqa: E402
from httpx import AsyncClient  # noqa: E402
from sqlalchemy import update  # noqa: E402

from conftest import (  # noqa: E402
    auth_headers,
    make_agent_account,
    make_client_under_agent,
)
from core.database import db_manager  # noqa: E402
from models.clients import Clients  # noqa: E402


async def _set_mid_cycle(client_id: int, next_billing_date: str):
    """Pin the client's current period end so days-remaining is deterministic."""
    async with db_manager.async_session_maker() as db:
        await db.execute(
            update(Clients)
            .where(Clients.id == client_id)
            .values(next_billing_date=next_billing_date)
        )
        await db.commit()


@pytest.mark.asyncio
async def test_upgrade_mid_cycle_charges_proration_then_bills_new_fee(client: AsyncClient):
    from datetime import datetime, timedelta, timezone

    _agent, agent_token, agent_id = await make_agent_account(client)
    _cl, client_token, client_id = await make_client_under_agent(client, agent_id)
    set_url = f"/api/v1/tenant/agent/clients/{client_id}/subscription"

    # Agent puts the client on a 200/month plan with half the monthly cycle left.
    resp = await client.put(
        set_url,
        headers=auth_headers(agent_token),
        json={"subscription_fee": 200.0, "billing_cycle": "monthly"},
    )
    assert resp.status_code == 200, resp.text
    # Anchor to the actual current date so exactly 15 days of the 30-day cycle
    # remain regardless of when the suite runs — the handler measures the unused
    # remainder against today (UTC), not a fixed calendar date.
    fifteen_days_out = (
        datetime.now(timezone.utc).date() + timedelta(days=15)
    ).isoformat()
    await _set_mid_cycle(client_id, fifteen_days_out)

    # Mid-cycle upgrade to 300 -> prorated charge of (300-200)*15/30 = +50.
    upgraded = await client.put(
        set_url,
        headers=auth_headers(agent_token),
        json={"subscription_fee": 300.0},
    )
    assert upgraded.status_code == 200, upgraded.text
    body = upgraded.json()
    assert body["subscription_fee"] == 300.0
    latest = body["payments"][0]
    assert latest["method"] == "proration"
    assert latest["amount"] == 50.0

    # The next full invoice bills the new fee in full, not the prorated amount.
    pay = await client.post(
        "/api/v1/tenant/client/subscription/pay", headers=auth_headers(client_token)
    )
    assert pay.status_code == 200, pay.text
    assert pay.json()["payments"][0]["amount"] == 300.0


@pytest.mark.asyncio
async def test_downgrade_mid_cycle_records_a_proration_credit(client: AsyncClient):
    from datetime import datetime, timedelta, timezone

    _agent, agent_token, agent_id = await make_agent_account(client)
    _cl, _client_token, client_id = await make_client_under_agent(client, agent_id)
    set_url = f"/api/v1/tenant/agent/clients/{client_id}/subscription"

    resp = await client.put(
        set_url,
        headers=auth_headers(agent_token),
        json={"subscription_fee": 300.0, "billing_cycle": "monthly"},
    )
    assert resp.status_code == 200, resp.text
    # Anchor to the actual current date so exactly 15 days of the 30-day cycle
    # remain regardless of when the suite runs — the handler measures the unused
    # remainder against today (UTC), not a fixed calendar date.
    fifteen_days_out = (
        datetime.now(timezone.utc).date() + timedelta(days=15)
    ).isoformat()
    await _set_mid_cycle(client_id, fifteen_days_out)

    # Mid-cycle downgrade 300 -> 100 -> prorated credit of (100-300)*15/30 = -100.
    downgraded = await client.put(
        set_url,
        headers=auth_headers(agent_token),
        json={"subscription_fee": 100.0},
    )
    assert downgraded.status_code == 200, downgraded.text
    latest = downgraded.json()["payments"][0]
    assert latest["method"] == "proration"
    assert latest["amount"] == -100.0
