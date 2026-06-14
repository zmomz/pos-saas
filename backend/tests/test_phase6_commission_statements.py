"""RSL-02 (ISSUE-055): periodic agent commission statements.

``GET /tenant/agent/revenue`` summarizes an agent's settled-subscription
economics across *all* time. A statement adds the **period** dimension: one
statement per billing period, with line items by client, summing back to the
same gross/master/net the underlying ``commission_ledger`` rows carry (so the
statement reconciles). Reads are scoped to the caller's own agent rows — one
agent can never see another agent's statements (SEC-02).
"""
import uuid

import pytest

from conftest import auth_headers, register_user, unique_email
from core.database import db_manager
from models.agents import Agents
from models.clients import Clients
from models.commission_ledger import Commission_ledger
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


@pytest.mark.asyncio
async def test_statement_for_a_paid_period_lists_client_and_reconciles(client):
    _au, a_token, a_id, _pkg = await _make_agent_with_package(client, wholesale=80.0, slots=10)
    _cu, c_token, c_id = await _make_paying_client(client, agent_id=a_id, fee=15.0)
    assert (
        await client.post(
            "/api/v1/tenant/client/subscription/pay", headers=auth_headers(c_token)
        )
    ).status_code == 200

    resp = await client.get(
        "/api/v1/tenant/agent/commission/statements", headers=auth_headers(a_token)
    )
    assert resp.status_code == 200, resp.text
    statements = resp.json()["statements"]

    # One billing period was settled -> one statement.
    assert len(statements) == 1
    stmt = statements[0]
    assert stmt["period_start"]  # carries the period it covers
    assert stmt["collected"] == 15.0
    assert stmt["master_owed"] == 8.0
    assert stmt["net"] == 7.0
    assert stmt["payments"] == 1
    # The statement reconciles: master + net == collected.
    assert round(stmt["master_owed"] + stmt["net"], 2) == stmt["collected"]

    # Line items by client.
    assert len(stmt["by_client"]) == 1
    line = stmt["by_client"][0]
    assert line["client_id"] == c_id
    assert line["business_name"] == "Corner Shop"
    assert line["collected"] == 15.0
    assert line["master_owed"] == 8.0
    assert line["net"] == 7.0


async def _seed_ledger(agent_user_id, agent_id, client_id, *, period_start, gross, master, net):
    """Insert one commission_ledger row for a given billing period."""
    async with db_manager.async_session_maker() as db:
        db.add(
            Commission_ledger(
                user_id=agent_user_id,
                agent_id=agent_id,
                client_id=client_id,
                subscription_payment_id=0,
                gross=gross,
                master_cut=master,
                agent_net=net,
                billing_cycle="monthly",
                period_start=period_start,
                period_end=period_start,
            )
        )
        await db.commit()


@pytest.mark.asyncio
async def test_statements_split_by_period_and_owner_scoped(client):
    a_user, a_token, a_id, _pkg = await _make_agent_with_package(client, wholesale=80.0, slots=10)
    _cu, _ct, c_id = await _make_paying_client(client, agent_id=a_id, fee=15.0)

    # Two distinct billing periods for the same client.
    await _seed_ledger(a_user["id"], a_id, c_id, period_start="2026-05-01", gross=15.0, master=8.0, net=7.0)
    await _seed_ledger(a_user["id"], a_id, c_id, period_start="2026-06-01", gross=15.0, master=8.0, net=7.0)

    # A different agent's row in the same period must not bleed in.
    b_user, _bt, b_id, _pkg2 = await _make_agent_with_package(client, wholesale=350.0, slots=50)
    _cu2, _ct2, c2_id = await _make_paying_client(client, agent_id=b_id, fee=20.0)
    await _seed_ledger(b_user["id"], b_id, c2_id, period_start="2026-06-01", gross=20.0, master=7.0, net=13.0)

    resp = await client.get(
        "/api/v1/tenant/agent/commission/statements", headers=auth_headers(a_token)
    )
    assert resp.status_code == 200, resp.text
    statements = resp.json()["statements"]

    # Two periods -> two statements, newest first; agent B's row excluded.
    assert [s["period_start"] for s in statements] == ["2026-06-01", "2026-05-01"]
    for stmt in statements:
        assert stmt["collected"] == 15.0
        assert stmt["master_owed"] == 8.0
        assert stmt["net"] == 7.0
        assert round(stmt["master_owed"] + stmt["net"], 2) == stmt["collected"]


@pytest.mark.asyncio
async def test_client_cannot_read_agent_statements(client):
    _au, _at, a_id, _pkg = await _make_agent_with_package(client, wholesale=80.0, slots=10)
    _cu, c_token, _cid = await _make_paying_client(client, agent_id=a_id, fee=15.0)
    denied = await client.get(
        "/api/v1/tenant/agent/commission/statements", headers=auth_headers(c_token)
    )
    assert denied.status_code == 403
