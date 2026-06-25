"""CL-06 (F-028): subscription dunning state machine.

A failed subscription charge must not hard-suspend immediately — it walks the
account active -> past_due -> dunning -> suspended over a retry schedule, and a
successful retry / pay recovers it to active. The sweep is agent-triggered and
owner-scoped (an agent only duns their own merchants, SEC-02).
"""
import uuid

import pytest
from sqlalchemy import select

from conftest import (
    auth_headers,
    make_agent_account,
    register_user,
    unique_email,
)
from core.database import db_manager
from models.audit_logs import Audit_logs
from models.clients import Clients
from models.subscription_payments import Subscription_payments
from services.dunning import next_dunning_state
from services.subscription_billing import SubscriptionChargeError


async def _make_overdue_client(client, *, agent_id: int, fee: float = 15.0, status: str = "active"):
    """Register a client login + a Clients row under ``agent_id`` whose billing
    date is already in the past (so the dunning sweep selects it)."""
    email = unique_email()
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123", "name": "Merchant"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    user, token = body["user"], body["token"]
    async with db_manager.async_session_maker() as db:
        merchant = Clients(
            user_id=user["id"],
            agent_id=agent_id,
            business_name="Corner Shop",
            email=email,
            subscription_fee=fee,
            billing_cycle="monthly",
            subscription_status=status,
            next_billing_date="2000-01-01",  # long past -> due
            is_active=True,
            dunning_attempts=0,
            invoice_counter=0,
        )
        db.add(merchant)
        await db.commit()
        await db.refresh(merchant)
        return user, token, merchant.id


async def _client_row(client_id: int) -> Clients:
    async with db_manager.async_session_maker() as db:
        return (
            await db.execute(select(Clients).where(Clients.id == client_id))
        ).scalar_one()


def test_next_dunning_state_walks_past_due_then_dunning_then_suspended():
    # Pure transition table with the default 3-retry schedule.
    attempts, status = 0, "active"

    t1 = next_dunning_state(status, attempts, charge_ok=False, max_retries=3)
    assert (t1.status, t1.attempts, t1.is_active) == ("past_due", 1, True)

    t2 = next_dunning_state(t1.status, t1.attempts, charge_ok=False, max_retries=3)
    assert (t2.status, t2.attempts, t2.is_active) == ("dunning", 2, True)

    t3 = next_dunning_state(t2.status, t2.attempts, charge_ok=False, max_retries=3)
    assert (t3.status, t3.attempts, t3.is_active) == ("suspended", 3, False)

    # A successful charge at any point recovers to active and resets the counter.
    recovered = next_dunning_state("dunning", 2, charge_ok=True, max_retries=3)
    assert (recovered.status, recovered.attempts, recovered.is_active) == ("active", 0, True)


@pytest.mark.asyncio
async def test_failed_charge_walks_client_past_due_to_suspended(client, monkeypatch):
    _au, a_token, a_id = await make_agent_account(client)
    _cu, _ct, client_id = await _make_overdue_client(client, agent_id=a_id)

    async def _decline(*args, **kwargs):
        raise SubscriptionChargeError("card declined")

    # Force every retry to fail so the account escalates through the schedule.
    monkeypatch.setattr("services.dunning.charge_subscription", _decline)

    # Sweep #1 -> past_due
    r1 = await client.post(
        "/api/v1/tenant/agent/billing/run-dunning", headers=auth_headers(a_token)
    )
    assert r1.status_code == 200, r1.text
    assert r1.json()["past_due"] == 1
    row = await _client_row(client_id)
    assert row.subscription_status == "past_due"
    assert row.dunning_attempts == 1
    assert row.is_active is True
    assert row.grace_deadline is not None

    # Sweep #2 -> dunning
    r2 = await client.post(
        "/api/v1/tenant/agent/billing/run-dunning", headers=auth_headers(a_token)
    )
    assert r2.json()["dunning"] == 1
    row = await _client_row(client_id)
    assert row.subscription_status == "dunning"
    assert row.dunning_attempts == 2
    assert row.is_active is True

    # Sweep #3 -> suspended (grace exhausted, blocked at auth)
    r3 = await client.post(
        "/api/v1/tenant/agent/billing/run-dunning", headers=auth_headers(a_token)
    )
    assert r3.json()["suspended"] == 1
    row = await _client_row(client_id)
    assert row.subscription_status == "suspended"
    assert row.dunning_attempts == 3
    assert row.is_active is False

    # Sweep #4 -> the suspended account is terminal and no longer swept.
    r4 = await client.post(
        "/api/v1/tenant/agent/billing/run-dunning", headers=auth_headers(a_token)
    )
    assert r4.json()["processed"] == 0

    # The escalation left an audit trail.
    async with db_manager.async_session_maker() as db:
        audits = (
            await db.execute(
                select(Audit_logs).where(
                    Audit_logs.entity_type == "clients",
                    Audit_logs.entity_id == str(client_id),
                    Audit_logs.action.like("DUNNING_%"),
                )
            )
        ).scalars().all()
    actions = {a.action for a in audits}
    assert {"DUNNING_PAST_DUE", "DUNNING_DUNNING", "DUNNING_SUSPENDED"} <= actions


@pytest.mark.asyncio
async def test_successful_retry_recovers_and_records_payment(client):
    # No Moyasar keys configured -> charge settles through the sandbox gateway, so
    # a sweep over a past_due account recovers it.
    _au, a_token, a_id = await make_agent_account(client)
    _cu, _ct, client_id = await _make_overdue_client(
        client, agent_id=a_id, status="dunning"
    )
    # Pretend two prior retries already failed.
    async with db_manager.async_session_maker() as db:
        merchant = (
            await db.execute(select(Clients).where(Clients.id == client_id))
        ).scalar_one()
        merchant.dunning_attempts = 2
        merchant.grace_deadline = "2000-01-08"
        await db.commit()

    resp = await client.post(
        "/api/v1/tenant/agent/billing/run-dunning", headers=auth_headers(a_token)
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["recovered"] == 1

    row = await _client_row(client_id)
    assert row.subscription_status == "active"
    assert row.dunning_attempts == 0
    assert row.grace_deadline is None
    assert row.is_active is True
    assert row.next_billing_date != "2000-01-01"  # billing advanced

    async with db_manager.async_session_maker() as db:
        payments = (
            await db.execute(
                select(Subscription_payments).where(
                    Subscription_payments.client_id == client_id
                )
            )
        ).scalars().all()
    assert len(payments) == 1


@pytest.mark.asyncio
async def test_run_dunning_is_owner_scoped(client, monkeypatch):
    _au, a_token, a_id = await make_agent_account(client)
    _bu, _bt, b_id = await make_agent_account(client)
    # An overdue client belongs to agent B.
    _cu, _ct, b_client_id = await _make_overdue_client(client, agent_id=b_id)

    async def _decline(*args, **kwargs):
        raise SubscriptionChargeError("card declined")

    monkeypatch.setattr("services.dunning.charge_subscription", _decline)

    # Agent A's sweep must not touch agent B's merchant.
    r = await client.post(
        "/api/v1/tenant/agent/billing/run-dunning", headers=auth_headers(a_token)
    )
    assert r.status_code == 200
    assert r.json()["processed"] == 0
    row = await _client_row(b_client_id)
    assert row.subscription_status == "active"
    assert row.dunning_attempts == 0

    # A client (non-agent) cannot run a dunning sweep.
    _user, c_token, _cid = await _make_overdue_client(client, agent_id=a_id)
    denied = await client.post(
        "/api/v1/tenant/agent/billing/run-dunning", headers=auth_headers(c_token)
    )
    assert denied.status_code == 403
