"""MA-08 / RSL-08 / RPT-09 (F-023): master platform-economics rollup.

The master operator console must surface platform-wide economics — total agents,
active clients, MRR, churn, and a revenue-by-agent leaderboard — aggregated from
the subscription/commission data. Before this finding, ``routers/tenant.py``
master routes stopped at agents/slots/tax-rate and the dashboard had no economics
at all. ``GET /tenant/master/economics`` is master-only (an agent/client gets 403,
SEC-02) and aggregated in SQL (OPS-05, no load-everything).
"""
import uuid

import pytest

from conftest import (
    auth_headers,
    make_master_account,
    register_user,
    unique_email,
)
from core.database import db_manager
from models.agents import Agents
from models.clients import Clients
from models.packages import Packages


async def _make_agent_with_package(client, *, wholesale: float, slots: int):
    """Register an agent login + a package + the owning Agents row.

    Returns (agent_user, agent_token, agent_id, package_id).
    """
    user, token, _ = await register_user(client)
    async with db_manager.async_session_maker() as db:
        pkg = Packages(
            name=f"Pkg-{uuid.uuid4().hex[:6]}",
            client_slots=slots,
            wholesale_price=wholesale,
            suggested_retail_price=15.0,
            is_active=True,
        )
        db.add(pkg)
        await db.commit()
        await db.refresh(pkg)

        agent = Agents(
            user_id=user["id"],
            company_name="Reseller Co",
            email=unique_email(),
            package_type=pkg.id,
            used_slots=0,
            is_active=True,
        )
        db.add(agent)
        await db.commit()
        await db.refresh(agent)
        return user, token, agent.id, pkg.id


async def _make_paying_client(
    client, *, agent_id: int, fee: float, cycle: str = "monthly", status: str = "active"
):
    """Register a client login + a Clients row under ``agent_id`` with a fee.

    Returns (client_user, client_token, client_id).
    """
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
            billing_cycle=cycle,
            subscription_status=status,
            is_active=True,
            invoice_counter=0,
        )
        db.add(merchant)
        await db.commit()
        await db.refresh(merchant)
        return user, token, merchant.id


@pytest.mark.asyncio
async def test_master_economics_rollup_per_agent_and_mrr(client):
    # An agent with a monthly client (fee 15) and a yearly client (fee 120 -> 10/mo).
    _au, _at, agent_id, _pkg = await _make_agent_with_package(client, wholesale=80.0, slots=10)
    _cu, c_token, _cid = await _make_paying_client(
        client, agent_id=agent_id, fee=15.0, cycle="monthly"
    )
    await _make_paying_client(client, agent_id=agent_id, fee=120.0, cycle="yearly")
    # A suspended client under the same agent contributes to churn, not MRR.
    await _make_paying_client(
        client, agent_id=agent_id, fee=99.0, cycle="monthly", status="suspended"
    )

    # The monthly client pays once -> one subscription payment (the agent's GMV).
    assert (
        await client.post(
            "/api/v1/tenant/client/subscription/pay", headers=auth_headers(c_token)
        )
    ).status_code == 200

    _mu, m_token = await make_master_account(client)
    resp = await client.get(
        "/api/v1/tenant/master/economics", headers=auth_headers(m_token)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # The economics shape carries the MA-08 signals.
    for key in ("mrr", "churn_rate", "by_agent", "total_agents", "active_clients"):
        assert key in body

    # Find this agent's leaderboard row and assert its scoped numbers exactly.
    row = next((a for a in body["by_agent"] if a["agent_id"] == agent_id), None)
    assert row is not None, "the agent must appear in the revenue-by-agent rollup"
    # 3 clients (2 live + 1 suspended); 2 active -> MRR = 15 (monthly) + 10 (120/12).
    assert row["total_clients"] == 3
    assert row["active_clients"] == 2
    assert row["mrr"] == 25.0
    # The single settled payment is the agent's GMV; he has paid no quota fee yet.
    assert row["collected"] == 15.0
    assert row["quota_paid"] == 0.0
    assert row["payments"] == 1

    # Platform's own revenue is the quota fees agents paid us (none here).
    assert body["platform_revenue"] == 0.0
    # Platform MRR includes this agent's 25, and churn is in [0, 1].
    assert body["mrr"] >= 25.0
    assert 0.0 <= body["churn_rate"] <= 1.0
    assert body["arr"] == round(body["mrr"] * 12, 2)


@pytest.mark.asyncio
async def test_master_economics_is_master_only(client):
    # An agent cannot read platform economics.
    _au, a_token, _agent_id, _pkg = await _make_agent_with_package(
        client, wholesale=80.0, slots=10
    )
    denied_agent = await client.get(
        "/api/v1/tenant/master/economics", headers=auth_headers(a_token)
    )
    assert denied_agent.status_code == 403

    # Neither can a client merchant.
    _cu, c_token, _cid = await _make_paying_client(client, agent_id=_agent_id, fee=15.0)
    denied_client = await client.get(
        "/api/v1/tenant/master/economics", headers=auth_headers(c_token)
    )
    assert denied_client.status_code == 403
