"""ISSUE-052: always-on billing scheduler (dunning/retry auto-sweep).

The dunning/retry logic used to run only on an agent's manual trigger
(POST /tenant/agent/billing/run-dunning). These tests cover the always-on path:
a platform-wide sweep (services.dunning.run_global_dunning) that advances overdue
subscriptions across ALL agents, the scheduler entry point that runs it without a
manual trigger (services.billing_scheduler.run_billing_sweep_once), and that the
whole thing is idempotent.
"""
import pytest
from sqlalchemy import select

from conftest import auth_headers, make_agent_account, register_user, unique_email
from core.database import db_manager
from models.clients import Clients
from models.subscription_payments import Subscription_payments
from services.subscription_billing import SubscriptionChargeError


async def _make_overdue_client(client, *, agent_id: int, fee: float = 15.0, status: str = "active"):
    """A Clients row under ``agent_id`` whose billing date is long past (so the
    sweep selects it)."""
    email = unique_email()
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123", "name": "Merchant"},
    )
    assert resp.status_code == 201, resp.text
    user = resp.json()["user"]
    async with db_manager.async_session_maker() as db:
        merchant = Clients(
            user_id=user["id"],
            agent_id=agent_id,
            business_name="Corner Shop",
            email=email,
            subscription_fee=fee,
            billing_cycle="monthly",
            subscription_status=status,
            next_billing_date="2000-01-01",
            is_active=True,
            dunning_attempts=0,
            invoice_counter=0,
        )
        db.add(merchant)
        await db.commit()
        await db.refresh(merchant)
        return merchant.id


async def _client_row(client_id: int) -> Clients:
    async with db_manager.async_session_maker() as db:
        return (
            await db.execute(select(Clients).where(Clients.id == client_id))
        ).scalar_one()


@pytest.mark.asyncio
async def test_global_sweep_advances_overdue_clients_across_all_agents(client, monkeypatch):
    """The platform-wide sweep is NOT owner-scoped: one pass advances every
    overdue merchant regardless of which agent owns it (AC2)."""
    from services.dunning import run_global_dunning

    _au, _at, a_id = await make_agent_account(client)
    _bu, _bt, b_id = await make_agent_account(client)
    a_client = await _make_overdue_client(client, agent_id=a_id)
    b_client = await _make_overdue_client(client, agent_id=b_id)

    async def _decline(*args, **kwargs):
        raise SubscriptionChargeError("card declined")

    monkeypatch.setattr("services.dunning.charge_subscription", _decline)

    async with db_manager.async_session_maker() as db:
        summary = await run_global_dunning(db, actor_user_id="system:test")

    # Both merchants were swept in one pass despite belonging to different agents
    # (the sweep is platform-wide, not owner-scoped). The shared session DB may
    # hold other overdue rows, so assert on the seeded pair, not on exact totals.
    assert summary["processed"] >= 2
    for cid in (a_client, b_client):
        row = await _client_row(cid)
        assert row.subscription_status == "past_due"
        assert row.dunning_attempts == 1


@pytest.mark.asyncio
async def test_global_sweep_is_idempotent(client):
    """Re-running the sweep does not double-charge or double-advance (AC3). With no
    Moyasar keys configured the charge settles through the sandbox gateway, so the
    first pass recovers the merchant and advances billing; the second pass finds it
    already settled this period and records nothing new."""
    from services.dunning import run_global_dunning

    _au, _at, a_id = await make_agent_account(client)
    cid = await _make_overdue_client(client, agent_id=a_id, status="past_due")

    async with db_manager.async_session_maker() as db:
        await run_global_dunning(db, actor_user_id="system:test")

    row = await _client_row(cid)
    assert row.subscription_status == "active"  # recovered this period
    advanced_billing = row.next_billing_date
    assert advanced_billing != "2000-01-01"  # billing moved into the future

    # Second pass: the recovered, now future-dated merchant is no longer overdue,
    # so it is neither advanced again nor charged again.
    async with db_manager.async_session_maker() as db:
        await run_global_dunning(db, actor_user_id="system:test")

    row = await _client_row(cid)
    assert row.next_billing_date == advanced_billing  # not advanced again

    async with db_manager.async_session_maker() as db:
        payments = (
            await db.execute(
                select(Subscription_payments).where(
                    Subscription_payments.client_id == cid
                )
            )
        ).scalars().all()
    assert len(payments) == 1  # not double-charged


@pytest.mark.asyncio
async def test_scheduler_entry_point_runs_sweep_without_manual_trigger(client, monkeypatch):
    """The scheduled job's tick (run_billing_sweep_once) drains the backlog with no
    agent auth / manual HTTP trigger — it opens its own session and sweeps (AC1)."""
    from services.billing_scheduler import run_billing_sweep_once

    _au, _at, a_id = await make_agent_account(client)
    cid = await _make_overdue_client(client, agent_id=a_id)

    async def _decline(*args, **kwargs):
        raise SubscriptionChargeError("card declined")

    monkeypatch.setattr("services.dunning.charge_subscription", _decline)

    summary = await run_billing_sweep_once()

    # The tick runs both rails; the merchant subscription sweep drained the backlog.
    assert summary["merchant_subscriptions"]["processed"] >= 1
    row = await _client_row(cid)
    assert row.subscription_status == "past_due"
    assert row.dunning_attempts == 1


def test_scheduler_is_disabled_by_default(monkeypatch):
    """Starting the scheduler is a no-op (returns None) unless explicitly enabled,
    so dev/CI never spawns a background charger."""
    from services import billing_scheduler

    monkeypatch.delenv("BILLING_SCHEDULER_ENABLED", raising=False)
    monkeypatch.setattr(
        billing_scheduler.settings, "billing_scheduler_enabled", False, raising=False
    )
    assert billing_scheduler.start_billing_scheduler() is None
