"""Periodic agent subscription-collection statements.

``GET /tenant/agent/revenue`` summarizes an agent's settled-subscription revenue
across *all* time. A statement adds the **period** dimension: one statement per
billing period, with line items by client, summing back to the underlying
``subscription_payments`` rows. This revenue is entirely the agent's (the platform
takes no cut — the platform's revenue is the wholesale quota the agent buys, Rail
1), so there is no master/net split. Reads are scoped to the caller's own clients —
one agent can never see another agent's statements (SEC-02).
"""
import uuid

import pytest

from conftest import auth_headers, register_user, unique_email
from core.database import db_manager
from models.agents import Agents
from models.clients import Clients
from models.packages import Packages
from models.subscription_payments import Subscription_payments


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
async def test_statement_for_a_paid_period_lists_client(client):
    _au, a_token, a_id, _pkg = await _make_agent_with_package(client, wholesale=80.0, slots=10)
    _cu, c_token, c_id = await _make_paying_client(client, agent_id=a_id, fee=15.0)
    # With no Moyasar keys configured (test env), the pay path settles through the
    # deterministic sandbox gateway and records the payment.
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
    assert stmt["payments"] == 1

    # Line items by client.
    assert len(stmt["by_client"]) == 1
    line = stmt["by_client"][0]
    assert line["client_id"] == c_id
    assert line["business_name"] == "Corner Shop"
    assert line["collected"] == 15.0


async def _seed_payment(agent_user_id, client_id, *, period_start, amount):
    """Insert one subscription_payments row for a given billing period."""
    async with db_manager.async_session_maker() as db:
        db.add(
            Subscription_payments(
                user_id=agent_user_id,
                client_id=client_id,
                amount=amount,
                billing_cycle="monthly",
                period_start=period_start,
                period_end=period_start,
                method="moyasar",
            )
        )
        await db.commit()


@pytest.mark.asyncio
async def test_statements_split_by_period_and_owner_scoped(client):
    a_user, a_token, a_id, _pkg = await _make_agent_with_package(client, wholesale=80.0, slots=10)
    _cu, _ct, c_id = await _make_paying_client(client, agent_id=a_id, fee=15.0)

    # Two distinct billing periods for the same client.
    await _seed_payment(a_user["id"], c_id, period_start="2026-05-01", amount=15.0)
    await _seed_payment(a_user["id"], c_id, period_start="2026-06-01", amount=15.0)

    # A different agent's payment in the same period must not bleed in.
    b_user, _bt, b_id, _pkg2 = await _make_agent_with_package(client, wholesale=350.0, slots=50)
    _cu2, _ct2, c2_id = await _make_paying_client(client, agent_id=b_id, fee=20.0)
    await _seed_payment(b_user["id"], c2_id, period_start="2026-06-01", amount=20.0)

    resp = await client.get(
        "/api/v1/tenant/agent/commission/statements", headers=auth_headers(a_token)
    )
    assert resp.status_code == 200, resp.text
    statements = resp.json()["statements"]

    # Two periods -> two statements, newest first; agent B's payment excluded.
    assert [s["period_start"] for s in statements] == ["2026-06-01", "2026-05-01"]
    for stmt in statements:
        assert stmt["collected"] == 15.0


@pytest.mark.asyncio
async def test_client_cannot_read_agent_statements(client):
    _au, _at, a_id, _pkg = await _make_agent_with_package(client, wholesale=80.0, slots=10)
    _cu, c_token, _cid = await _make_paying_client(client, agent_id=a_id, fee=15.0)
    denied = await client.get(
        "/api/v1/tenant/agent/commission/statements", headers=auth_headers(c_token)
    )
    assert denied.status_code == 403
