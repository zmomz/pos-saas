"""REV-04: the recurring-charge idempotency key is the billing-period boundary,
not the calendar day the charge happens to run.

FIN-04 deduped a settled period on ``(client_id, period_key)`` but keyed it on
``now.date()``. That blocks a same-day double-click, but a cross-midnight
concurrent race (one charge at 23:59, its twin at 00:01 the next day) computes
two *different* per-day keys for the *same* billing period, so the DB unique
constraint never fires and the card is charged twice.

The fix keys the settled payment on the period boundary being settled — the
subscriber's current ``next_billing_date`` — which both racers read identically
regardless of the wall-clock day, so the second insert collides and reconciles.
"""
from datetime import datetime, timezone

import pytest
from sqlalchemy import delete, func, select, update

from conftest import make_agent_account, register_user, unique_email
from core.database import db_manager
from models.clients import Clients
from models.subscription_payments import Subscription_payments


@pytest.fixture
async def _purge_payments():
    """The shared test DB has no per-test isolation; delete the settled payment
    rows this test inserts so they don't leak into platform-revenue rollups."""
    async with db_manager.async_session_maker() as db:
        sub_max = (await db.execute(select(func.max(Subscription_payments.id)))).scalar() or 0
    yield
    async with db_manager.async_session_maker() as db:
        await db.execute(delete(Subscription_payments).where(Subscription_payments.id > sub_max))
        await db.commit()


def test_period_key_is_the_billing_boundary_not_the_calendar_day():
    """The key is the period boundary (current ``next_billing_date``) regardless of
    the period_end a given charge computes — so two charges that straddle midnight
    (and thus compute different period_end anchors) still collide on it."""
    from core.billing_period import billing_period_key

    boundary = "2026-07-15"
    # Two charges across midnight compute different period_end values, yet both read
    # the same current next_billing_date — the key follows the boundary, not the day.
    k1 = billing_period_key(boundary, period_end="2026-07-29")
    k2 = billing_period_key(boundary, period_end="2026-07-30")

    assert k1 == boundary
    assert k1 == k2  # stable across the calendar-day flip — the race collides


def test_period_key_keys_an_overdue_period_by_its_due_date():
    """An overdue period is identified by its (past) due date, not the day the
    dunning retry happens to land on (which drives a different period_end)."""
    from core.billing_period import billing_period_key

    assert billing_period_key("2026-06-01", period_end="2026-07-29") == "2026-06-01"
    assert billing_period_key("2026-06-01", period_end="2026-07-30") == "2026-06-01"


def test_period_key_falls_back_to_period_end_when_no_boundary_recorded():
    """A brand-new subscription's first charge has no prior boundary, so the key is
    the period_end being established. That equals the next_billing_date the charge
    advances to, so a same-day re-pay reads it back and reconciles to one period."""
    from core.billing_period import billing_period_key

    assert billing_period_key(None, period_end="2026-07-27") == "2026-07-27"
    assert billing_period_key("not-a-date", period_end="2026-07-27") == "2026-07-27"


@pytest.mark.asyncio
async def test_cross_midnight_dunning_race_charges_once(client, monkeypatch, _purge_payments):
    """AC: two dunning retries for the SAME overdue period that straddle midnight
    settle the card exactly once. The second (next-day) retry reads the same
    pre-advance ``next_billing_date`` boundary as the first, so its settled-period
    key collides and it reconciles instead of charging a second time.

    With the old per-calendar-day key the two retries had distinct keys and the
    second would charge again — the regression this guards.
    """
    from services.dunning import run_client_dunning
    from services.subscription_billing import ChargeResult

    boundary = "2026-06-01"  # the overdue period's due date (the period boundary)

    _au, _at, agent_id = await make_agent_account(client)
    user, _token, _ = await register_user(client)
    async with db_manager.async_session_maker() as db:
        merchant = Clients(
            user_id=user["id"],
            agent_id=agent_id,
            business_name="Race Shop",
            email=unique_email(),
            subscription_fee=20.0,
            billing_cycle="monthly",
            subscription_status="dunning",
            next_billing_date=boundary,
            is_active=True,
            dunning_attempts=1,
            invoice_counter=0,
        )
        db.add(merchant)
        await db.commit()
        client_id = merchant.id

    async def _approve(*args, **kwargs):
        return ChargeResult(charged=True, status="paid", method="sandbox", reference="ref_race")

    monkeypatch.setattr("services.dunning.charge_subscription", _approve)

    # Retry #1 — 23:59 on day one. Charges, records the settled period, advances.
    async with db_manager.async_session_maker() as db:
        m = (await db.execute(select(Clients).where(Clients.id == client_id))).scalar_one()
        r1 = await run_client_dunning(
            db, m, actor_user_id="system:test",
            now=datetime(2026, 6, 29, 23, 59, tzinfo=timezone.utc),
        )
        await db.commit()
    assert r1["action"] == "recovered", r1

    # Simulate the concurrent racer: its transaction read the pre-advance billing
    # date. Reset the boundary to model that read, then run retry #2 at 00:01 the
    # NEXT day. A per-day key would differ here and double-charge.
    async with db_manager.async_session_maker() as db:
        await db.execute(
            update(Clients).where(Clients.id == client_id).values(next_billing_date=boundary)
        )
        await db.commit()

    async with db_manager.async_session_maker() as db:
        m = (await db.execute(select(Clients).where(Clients.id == client_id))).scalar_one()
        r2 = await run_client_dunning(
            db, m, actor_user_id="system:test",
            now=datetime(2026, 6, 30, 0, 1, tzinfo=timezone.utc),
        )
        await db.commit()
    assert r2["action"] == "skipped", r2  # reconciled to the already-settled period

    async with db_manager.async_session_maker() as db:
        rows = (
            await db.execute(
                select(Subscription_payments).where(Subscription_payments.client_id == client_id)
            )
        ).scalars().all()
    settled = [p for p in rows if p.method in ("moyasar", "sandbox")]
    assert len(settled) == 1, f"expected one settled charge across midnight, got {len(settled)}"
    assert settled[0].period_key == boundary  # keyed on the boundary, not the day
