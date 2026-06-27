"""ISSUE-182 — reserve-then-charge closes the double-charge window.

The Moyasar "idempotency key" (FIN-04, #134) is **metadata only** — Moyasar does
not dedupe on it. The local guard was a SELECT pre-check (``existing_*_payment``)
followed by ``charge`` and only THEN the unique-constraint ``record``. Two requests
that both pass the pre-check therefore each fire a *real* gateway charge; the
``(scope, period_key)`` unique constraint then rejects only the second INSERT — the
card is already billed twice while the ledger shows one row.

The fix mirrors the aggregator settle lock (REV-05): a committed reserve-then-charge.
The settling caller first INSERTs+commits a ``reserving`` placeholder keyed on
``(scope, period_key)``; the unique constraint is the compare-and-set, so exactly
one caller wins it and charges. A concurrent caller loses the INSERT and backs off
without charging. A decline releases the reservation so a later retry can charge,
and a reservation orphaned by a crash is reclaimed by a bounded stale-sweep.

These tests count *gateway* charges (not ledger rows — the unique constraint always
collapses the rows to one, which is exactly why row counts hid the bug).
"""
import asyncio
import uuid

import pytest
from sqlalchemy import delete, func, select, update

import services.payment_gateway as pg
from conftest import auth_headers, make_agent_account, make_client_under_agent
from core.database import db_manager
from models.agent_quota_payments import Agent_quota_payments
from models.agents import Agents
from models.subscription_payments import Subscription_payments


@pytest.fixture(autouse=True)
async def _purge_payments_created_here():
    """The shared test DB has no per-test isolation (TST-04); purge the payment rows
    each test inserts so platform-revenue rollups elsewhere stay clean."""
    async with db_manager.async_session_maker() as db:
        sub_max = (await db.execute(select(func.max(Subscription_payments.id)))).scalar() or 0
        quota_max = (await db.execute(select(func.max(Agent_quota_payments.id)))).scalar() or 0
    yield
    async with db_manager.async_session_maker() as db:
        await db.execute(delete(Subscription_payments).where(Subscription_payments.id > sub_max))
        await db.execute(delete(Agent_quota_payments).where(Agent_quota_payments.id > quota_max))
        await db.commit()


@pytest.fixture
def charge_spy(monkeypatch):
    """Count real gateway ``charge`` invocations across both billing rails."""
    calls = {"n": 0}
    original = pg.SandboxGateway.charge

    async def counting(self, *args, **kwargs):
        calls["n"] += 1
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(pg.SandboxGateway, "charge", counting)
    return calls


@pytest.mark.asyncio
async def test_concurrent_subscription_pay_charges_card_once(client, charge_spy):
    """AC#1 (Rail 2): two truly-concurrent ``/subscription/pay`` requests for the
    same period bill the card exactly once — the loser backs off without charging."""
    _u, agent_token, agent_id = await make_agent_account(client)
    _u2, client_token, client_id = await make_client_under_agent(client, agent_id)
    r = await client.put(
        f"/api/v1/tenant/agent/clients/{client_id}/subscription",
        json={"subscription_fee": 50.0, "billing_cycle": "monthly"},
        headers=auth_headers(agent_token),
    )
    assert r.status_code == 200, r.text

    async def pay():
        return await client.post(
            "/api/v1/tenant/client/subscription/pay", headers=auth_headers(client_token)
        )

    r1, r2 = await asyncio.gather(pay(), pay())
    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text

    assert charge_spy["n"] == 1, f"expected exactly ONE gateway charge, got {charge_spy['n']}"

    async with db_manager.async_session_maker() as db:
        rows = (
            await db.execute(
                select(Subscription_payments).where(
                    Subscription_payments.client_id == client_id
                )
            )
        ).scalars().all()
    settled = [p for p in rows if p.method in ("moyasar", "sandbox")]
    assert len(settled) == 1, f"expected one settled charge, got {len(settled)}"
    # No reservation placeholder is left behind once finalised.
    assert not [p for p in rows if p.method == "reserving"]


@pytest.mark.asyncio
async def test_concurrent_quota_pay_charges_agent_once(client, charge_spy):
    """AC#1 (Rail 1): two concurrent ``/agent/quota/pay`` requests for the same
    quota period bill the agent exactly once."""
    _user, agent_token, agent_id = await make_agent_account(client)
    async with db_manager.async_session_maker() as db:
        await db.execute(
            update(Agents)
            .where(Agents.id == agent_id)
            .values(quota_price=100.0, quota_cycle="monthly")
        )
        await db.commit()

    async def pay():
        return await client.post(
            "/api/v1/tenant/agent/quota/pay", headers=auth_headers(agent_token)
        )

    r1, r2 = await asyncio.gather(pay(), pay())
    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text

    assert charge_spy["n"] == 1, f"expected exactly ONE quota charge, got {charge_spy['n']}"

    async with db_manager.async_session_maker() as db:
        rows = (
            await db.execute(
                select(Agent_quota_payments).where(
                    Agent_quota_payments.agent_id == agent_id
                )
            )
        ).scalars().all()
    settled = [p for p in rows if p.method in ("moyasar", "sandbox")]
    assert len(settled) == 1, f"expected one settled quota charge, got {len(settled)}"
    assert not [p for p in rows if p.method == "reserving"]


@pytest.mark.asyncio
async def test_declined_charge_releases_reservation_for_retry(client, monkeypatch):
    """A decline must RELEASE the reservation so the period is open for a later retry,
    not leave the card permanently blocked from paying (ISSUE-182)."""
    _u, agent_token, agent_id = await make_agent_account(client)
    _u2, client_token, client_id = await make_client_under_agent(client, agent_id)
    r = await client.put(
        f"/api/v1/tenant/agent/clients/{client_id}/subscription",
        json={"subscription_fee": 50.0, "billing_cycle": "monthly"},
        headers=auth_headers(agent_token),
    )
    assert r.status_code == 200, r.text

    # First attempt declines.
    declines = {"on": True}
    original = pg.SandboxGateway.charge

    async def maybe_decline(self, *args, **kwargs):
        if declines["on"]:
            return pg.GatewayResult(
                approved=False, gateway=self.name, decline_reason="insufficient_funds"
            )
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(pg.SandboxGateway, "charge", maybe_decline)

    r1 = await client.post(
        "/api/v1/tenant/client/subscription/pay", headers=auth_headers(client_token)
    )
    assert r1.status_code == 402, r1.text

    # No reservation placeholder is left blocking the period.
    async with db_manager.async_session_maker() as db:
        rows = (
            await db.execute(
                select(Subscription_payments).where(
                    Subscription_payments.client_id == client_id
                )
            )
        ).scalars().all()
    assert not [p for p in rows if p.method == "reserving"], "decline left a stuck reservation"
    assert not [p for p in rows if p.method in ("moyasar", "sandbox")]

    # The retry now succeeds and charges exactly once.
    declines["on"] = False
    r2 = await client.post(
        "/api/v1/tenant/client/subscription/pay", headers=auth_headers(client_token)
    )
    assert r2.status_code == 200, r2.text
    async with db_manager.async_session_maker() as db:
        rows = (
            await db.execute(
                select(Subscription_payments).where(
                    Subscription_payments.client_id == client_id
                )
            )
        ).scalars().all()
    settled = [p for p in rows if p.method in ("moyasar", "sandbox")]
    assert len(settled) == 1, f"retry should settle once, got {len(settled)}"


@pytest.mark.asyncio
async def test_stale_reservation_is_reclaimed(client):
    """A reservation orphaned by a crash (settler died before finalise/release) is
    reclaimed by the bounded stale-sweep so its period is not blocked forever."""
    from datetime import datetime, timedelta, timezone

    from services.subscription_billing import release_stale_subscription_reservations

    _u, agent_token, agent_id = await make_agent_account(client)
    _u2, _ct, client_id = await make_client_under_agent(client, agent_id)

    async with db_manager.async_session_maker() as db:
        stale = Subscription_payments(
            user_id="u",
            client_id=client_id,
            amount=0,
            billing_cycle="monthly",
            period_start="2026-06-01",
            period_end="2026-07-01",
            period_key="2026-06-01",
            method="reserving",
            reference=None,
        )
        stale.created_at = datetime.now(timezone.utc) - timedelta(hours=2)
        db.add(stale)
        await db.commit()

    async with db_manager.async_session_maker() as db:
        reclaimed = await release_stale_subscription_reservations(db, threshold_seconds=600)
    assert reclaimed == 1

    async with db_manager.async_session_maker() as db:
        left = (
            await db.execute(
                select(Subscription_payments).where(
                    Subscription_payments.client_id == client_id,
                    Subscription_payments.method == "reserving",
                )
            )
        ).scalars().all()
    assert left == [], "stale reservation should have been reclaimed"


@pytest.mark.asyncio
async def test_dunning_sweep_does_not_charge_a_reserved_period(client, charge_spy):
    """The scheduler sweep must back off a period another settler is already holding
    (a manual pay in flight), so the two never both charge the card (ISSUE-182)."""
    from datetime import datetime, timezone

    from models.clients import Clients
    from services.dunning import run_global_dunning

    _u, _at, agent_id = await make_agent_account(client)
    _u2, _ct, client_id = await make_client_under_agent(client, agent_id)

    async with db_manager.async_session_maker() as db:
        await db.execute(
            update(Clients)
            .where(Clients.id == client_id)
            .values(
                subscription_fee=50.0,
                billing_cycle="monthly",
                subscription_status="past_due",
                next_billing_date="2026-06-01",
            )
        )
        # An in-flight reservation already holds this period (period_key == the
        # current next_billing_date boundary).
        db.add(
            Subscription_payments(
                user_id="u",
                client_id=client_id,
                amount=0,
                billing_cycle="monthly",
                period_start="2026-06-01",
                period_end="2026-07-01",
                period_key="2026-06-01",
                method="reserving",
                reference=None,
                created_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()

    async with db_manager.async_session_maker() as db:
        await run_global_dunning(db, now=datetime(2026, 6, 15, tzinfo=timezone.utc))

    assert charge_spy["n"] == 0, f"sweep charged a period under reservation ({charge_spy['n']})"
