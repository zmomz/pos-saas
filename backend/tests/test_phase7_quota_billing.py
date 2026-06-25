"""Rail 1: agent quota billing (the platform's own revenue).

The platform sells the agent a fixed-price quota of client slots; the agent pays
for it through the platform's Moyasar account against his card-on-file. With no
Moyasar keys configured (test env) the charge settles through the sandbox gateway.
A failed quota renewal walks the agent through dunning and, on suspension, cascades
to block the agent (and his merchants) at auth.
"""
import uuid

import pytest
from sqlalchemy import select

from conftest import auth_headers, make_master_account, register_user, unique_email
from core.database import db_manager
from models.agent_quota_payments import Agent_quota_payments
from models.agents import Agents
from models.packages import Packages


async def _master_creates_agent_from_package(client, *, wholesale: float, slots: int):
    """Master provisions an agent from a package; returns (agent_id, package_id)."""
    _mu, m_token = await make_master_account(client)
    async with db_manager.async_session_maker() as db:
        pkg = Packages(
            name=f"Pkg-{uuid.uuid4().hex[:6]}",
            client_slots=slots,
            wholesale_price=wholesale,
            suggested_retail_price=wholesale * 2,
            is_active=True,
        )
        db.add(pkg)
        await db.commit()
        await db.refresh(pkg)

    resp = await client.post(
        "/api/v1/tenant/master/agents",
        json={"company_name": "Reseller Co", "email": unique_email(), "package_id": pkg.id},
        headers=auth_headers(m_token),
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"], pkg.id


@pytest.mark.asyncio
async def test_provisioning_sets_quota_price_from_package(client):
    agent_id, _pkg = await _master_creates_agent_from_package(client, wholesale=80.0, slots=10)
    async with db_manager.async_session_maker() as db:
        agent = (await db.execute(select(Agents).where(Agents.id == agent_id))).scalar_one()
    assert agent.quota_price == 80.0
    assert agent.quota_cycle == "monthly"
    assert agent.quota_status == "active"
    assert agent.next_quota_billing_date  # an obligation was scheduled


@pytest.mark.asyncio
async def test_agent_pays_quota_records_payment(client):
    # Register an agent login directly and attach a priced quota.
    user, token, _ = await register_user(client)
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
            quota_status="active",
        )
        db.add(agent)
        await db.commit()
        await db.refresh(agent)
        agent_id = agent.id

    resp = await client.post("/api/v1/tenant/agent/quota/pay", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["quota_status"] == "active"
    assert len(body["payments"]) == 1
    assert body["payments"][0]["amount"] == 80.0

    async with db_manager.async_session_maker() as db:
        rows = (
            await db.execute(
                select(Agent_quota_payments).where(Agent_quota_payments.agent_id == agent_id)
            )
        ).scalars().all()
    assert len(rows) == 1
    assert rows[0].method in ("moyasar", "sandbox")


@pytest.mark.asyncio
async def test_quota_dunning_suspends_agent_and_cascades(client, monkeypatch):
    user, token, _ = await register_user(client)
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
            quota_dunning_attempts=2,  # one more failure suspends (default max 3)
            next_quota_billing_date="2000-01-01",
        )
        db.add(agent)
        await db.commit()
        await db.refresh(agent)
        agent_id = agent.id

    from services.quota_billing import QuotaChargeError, run_global_quota_dunning

    async def _decline(*args, **kwargs):
        raise QuotaChargeError("card declined")

    monkeypatch.setattr("services.quota_billing.charge_quota", _decline)

    async with db_manager.async_session_maker() as db:
        summary = await run_global_quota_dunning(db, actor_user_id="system:test")
    assert summary["processed"] >= 1

    async with db_manager.async_session_maker() as db:
        agent = (await db.execute(select(Agents).where(Agents.id == agent_id))).scalar_one()
    assert agent.quota_status == "suspended"
    assert agent.is_active is False  # cascade: agent (and his merchants) blocked
