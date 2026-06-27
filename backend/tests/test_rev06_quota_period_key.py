"""REV-06: the quota dunning sweep keys its Moyasar idempotency on the billing
period boundary, not the calendar day the sweep happens to run.

REV-04 (#177) keyed three of four recurring-charge sites on the period boundary
but missed the quota sweep: ``quota_billing.run_agent_quota_dunning`` recorded
the settled period on ``period_key`` (the boundary) yet still passed
``idempotency_key=f"quota-{agent.id}-{period_start}"`` (``now.date()``) to the
gateway. A cross-midnight race between a manual quota pay and the scheduler sweep
transports two *different* keys to Moyasar for the *same* period, defeating
reconciliation on the platform's own revenue rail.

The fix keys the gateway idempotency on the boundary too, so both racers send the
same key and Moyasar dedups the money.
"""
from datetime import datetime, timezone

import pytest
from sqlalchemy import delete, func, select

from conftest import register_user, unique_email
from core.database import db_manager
from models.agent_quota_payments import Agent_quota_payments
from models.agents import Agents


@pytest.fixture
async def _purge_quota_payments():
    async with db_manager.async_session_maker() as db:
        qmax = (await db.execute(select(func.max(Agent_quota_payments.id)))).scalar() or 0
    yield
    async with db_manager.async_session_maker() as db:
        await db.execute(delete(Agent_quota_payments).where(Agent_quota_payments.id > qmax))
        await db.commit()


@pytest.mark.asyncio
async def test_quota_sweep_keys_moyasar_idempotency_on_the_period_boundary(
    client, monkeypatch, _purge_quota_payments
):
    """AC: the idempotency key handed to the gateway is ``quota-{id}-{period_key}``
    (the overdue boundary) — NOT ``quota-{id}-{now.date()}``. With the per-day key,
    a manual pay and the sweep straddling midnight send distinct keys and Moyasar
    charges twice; keying on the boundary makes them collide on one charge."""
    from services.quota_billing import QuotaChargeResult, run_agent_quota_dunning

    boundary = "2000-01-01"  # an overdue quota period due date (the boundary)

    user, _token, _ = await register_user(client)
    async with db_manager.async_session_maker() as db:
        agent = Agents(
            user_id=user["id"],
            company_name="Reseller Co",
            email=unique_email(),
            package_type=10,
            used_slots=0,
            is_active=True,
            quota_price=80.0,
            quota_cycle="monthly",
            quota_status="dunning",
            quota_dunning_attempts=0,
            next_quota_billing_date=boundary,
        )
        db.add(agent)
        await db.commit()
        await db.refresh(agent)
        agent_id = agent.id

    captured = {}

    async def _approve(agent, *, idempotency_key=None, **kwargs):
        captured["idempotency_key"] = idempotency_key
        return QuotaChargeResult(
            charged=True, status="paid", method="sandbox", reference="ref_q"
        )

    monkeypatch.setattr("services.quota_billing.charge_quota", _approve)

    # Run the sweep on a calendar day that is NOT the boundary — so a per-day key
    # would read the run date, not the boundary.
    async with db_manager.async_session_maker() as db:
        agent = (await db.execute(select(Agents).where(Agents.id == agent_id))).scalar_one()
        result = await run_agent_quota_dunning(
            db, agent, actor_user_id="system:test",
            now=datetime(2026, 6, 30, 0, 1, tzinfo=timezone.utc),
        )
        await db.commit()

    assert result["action"] == "recovered", result
    assert captured["idempotency_key"] == f"quota-{agent_id}-{boundary}", (
        "quota sweep must key Moyasar idempotency on the period boundary, not the "
        f"calendar day; got {captured['idempotency_key']!r}"
    )
