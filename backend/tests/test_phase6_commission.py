"""RSL-01 (F-029): commission / revenue-split ledger.

When a client pays their subscription, the gross fee must be decomposed into the
platform master's cut (per-client amortized package wholesale) and the agent's
net margin, and one balanced ``commission_ledger`` row written atomically with
the payment. The agent can then see real margin via ``GET /tenant/agent/revenue``
— scoped to their own clients (SEC-02).
"""
import uuid

import pytest
from sqlalchemy import select

from conftest import auth_headers, register_user, unique_email
from core.database import db_manager
from models.agents import Agents
from models.clients import Clients
from models.commission_ledger import Commission_ledger
from models.packages import Packages
from services.commission import compute_commission_split


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


async def _make_paying_client(client, *, agent_id: int, fee: float, cycle: str = "monthly"):
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
            is_active=True,
            invoice_counter=0,
        )
        db.add(merchant)
        await db.commit()
        await db.refresh(merchant)
        return user, token, merchant.id


def test_compute_commission_split_invariant():
    # Starter: 80 wholesale over 10 slots -> 8 per client; fee 15 -> 8 + 7.
    master_cut, agent_net = compute_commission_split(15.0, 80.0, 10)
    assert master_cut == 8.0
    assert agent_net == 7.0
    assert round(master_cut + agent_net, 2) == 15.0

    # A loss-leader fee below wholesale clamps the master cut to the gross
    # (never negative agent_net), and the invariant still holds.
    m2, n2 = compute_commission_split(5.0, 80.0, 10)
    assert m2 == 5.0 and n2 == 0.0
    assert round(m2 + n2, 2) == 5.0

    # Unresolvable package (no slots) -> whole fee is the agent's.
    m3, n3 = compute_commission_split(12.0, 0.0, 0)
    assert m3 == 0.0 and n3 == 12.0


@pytest.mark.asyncio
async def test_subscription_pay_writes_one_balanced_commission_row(client):
    _au, _at, agent_id, pkg_id = await _make_agent_with_package(client, wholesale=80.0, slots=10)
    _cu, client_token, client_id = await _make_paying_client(client, agent_id=agent_id, fee=15.0)

    resp = await client.post(
        "/api/v1/tenant/client/subscription/pay", headers=auth_headers(client_token)
    )
    assert resp.status_code == 200, resp.text

    async with db_manager.async_session_maker() as db:
        rows = (
            await db.execute(
                select(Commission_ledger).where(Commission_ledger.client_id == client_id)
            )
        ).scalars().all()
        assert len(rows) == 1
        row = rows[0]
        assert row.agent_id == agent_id
        assert row.package_id == pkg_id
        assert row.gross == 15.0
        assert row.master_cut == 8.0
        assert row.agent_net == 7.0
        # The ledger reconciles: the split always sums back to the gross.
        assert round(row.master_cut + row.agent_net, 2) == row.gross
        assert row.subscription_payment_id is not None


@pytest.mark.asyncio
async def test_agent_revenue_aggregates_and_is_owner_scoped(client):
    # Agent A: one client paying 15 on the Starter package (master 8 / net 7).
    _au, a_token, a_id, _pkg = await _make_agent_with_package(client, wholesale=80.0, slots=10)
    _cu, c_token, _cid = await _make_paying_client(client, agent_id=a_id, fee=15.0)
    assert (
        await client.post(
            "/api/v1/tenant/client/subscription/pay", headers=auth_headers(c_token)
        )
    ).status_code == 200

    # A second agent with their own paying client must not bleed into A's totals.
    _bu, b_token, b_id, _pkg2 = await _make_agent_with_package(client, wholesale=350.0, slots=50)
    _cu2, c2_token, _cid2 = await _make_paying_client(client, agent_id=b_id, fee=20.0)
    assert (
        await client.post(
            "/api/v1/tenant/client/subscription/pay", headers=auth_headers(c2_token)
        )
    ).status_code == 200

    # Agent A sees only their own revenue.
    rev = await client.get("/api/v1/tenant/agent/revenue", headers=auth_headers(a_token))
    assert rev.status_code == 200, rev.text
    body = rev.json()
    assert body["collected"] == 15.0
    assert body["master_owed"] == 8.0
    assert body["net"] == 7.0
    assert body["payments"] == 1
    assert round(body["master_owed"] + body["net"], 2) == body["collected"]
    assert len(body["by_client"]) == 1

    # A client cannot reach the agent revenue endpoint.
    denied = await client.get(
        "/api/v1/tenant/agent/revenue", headers=auth_headers(c_token)
    )
    assert denied.status_code == 403
