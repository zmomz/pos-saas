"""ISSUE-245 (M9·Dashboards): enrich master/agent dashboard KPIs.

The master console must surface the buyer-expected SaaS economics — not just MRR
and churn, but ARR (already shipped), LTV (lifetime value, a real aggregate from
the live MRR/churn signals) and CAC (acquisition cost, honestly *unavailable*
until an acquisition-spend ledger exists rather than fabricated — FE-05 / #204
error honesty).

The agent dashboard must surface its own operating KPIs — active merchants,
merchant growth (new this period vs the prior period), trial expiry (merchants
whose trial ends soon) and a short revenue trend — all SQL/window-aggregated and
scoped to the caller's own merchants (SEC-02, OPS-05 no-load-everything).
"""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import update

from conftest import (
    auth_headers,
    make_agent_account,
    make_client_under_agent,
    make_master_account,
    unique_email,
)
from core.database import db_manager
from models.clients import Clients
from models.subscription_payments import Subscription_payments


async def _set_client(
    client_id: int,
    **values,
):
    """Patch a Clients row directly (created_at / trial_end / status / archived)."""
    async with db_manager.async_session_maker() as db:
        await db.execute(update(Clients).where(Clients.id == client_id).values(**values))
        await db.commit()


# ---------------------------------------------------------------- master LTV/CAC


@pytest.mark.asyncio
async def test_master_economics_reports_ltv_and_cac(client):
    """LTV is a real aggregate (ARPA / churn); CAC is honestly null (no spend feed)."""
    _au, _at, agent_id = await make_agent_account(client)
    # 3 active monthly merchants at fee 100 -> MRR 300, ARPA 100.
    for _ in range(3):
        _u, _t, cid = await make_client_under_agent(client, agent_id)
        await _set_client(cid, subscription_fee=100.0, billing_cycle="monthly",
                          subscription_status="active")
    # 1 suspended merchant -> churn_rate = 1/4 = 0.25.
    _u, _t, scid = await make_client_under_agent(client, agent_id)
    await _set_client(scid, subscription_fee=100.0, subscription_status="suspended")

    _mu, m_token = await make_master_account(client)
    resp = await client.get(
        "/api/v1/tenant/master/economics", headers=auth_headers(m_token)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["mrr"] == 300.0
    assert body["active_clients"] == 3
    assert body["churn_rate"] == 0.25
    # LTV = ARPA / churn = (300/3) / 0.25 = 400.
    assert body["ltv"] == 400.0
    # CAC has no acquisition-spend source yet -> honestly null, never a fabricated 0.
    assert "cac" in body
    assert body["cac"] is None


@pytest.mark.asyncio
async def test_master_ltv_is_null_without_churn(client):
    """With zero churn the lifetime is unbounded — report null, not infinity/0."""
    _au, _at, agent_id = await make_agent_account(client)
    _u, _t, cid = await make_client_under_agent(client, agent_id)
    await _set_client(cid, subscription_fee=100.0, subscription_status="active")

    _mu, m_token = await make_master_account(client)
    body = (
        await client.get("/api/v1/tenant/master/economics", headers=auth_headers(m_token))
    ).json()
    assert body["churn_rate"] == 0.0
    assert body["ltv"] is None


# ---------------------------------------------------------------- agent KPIs


@pytest.mark.asyncio
async def test_agent_dashboard_kpis_rollup(client):
    now = datetime.now()
    _au, a_token, agent_id = await make_agent_account(client)

    # Two active merchants created in the last 30 days (new growth).
    _u, _t, c_new1 = await make_client_under_agent(client, agent_id)
    _u, _t, c_new2 = await make_client_under_agent(client, agent_id)
    await _set_client(c_new1, created_at=now - timedelta(days=3),
                      subscription_status="active")
    await _set_client(c_new2, created_at=now - timedelta(days=10),
                      subscription_status="active")
    # One active merchant created 45 days ago (prior period, not "new").
    _u, _t, c_old = await make_client_under_agent(client, agent_id)
    await _set_client(c_old, created_at=now - timedelta(days=45),
                      subscription_status="active")
    # One suspended merchant (active count must exclude it).
    _u, _t, c_susp = await make_client_under_agent(client, agent_id)
    await _set_client(c_susp, created_at=now - timedelta(days=5),
                      subscription_status="suspended")
    # One archived merchant (excluded from every count).
    _u, _t, c_arch = await make_client_under_agent(client, agent_id)
    await _set_client(c_arch, created_at=now - timedelta(days=2),
                      archived_at=now.isoformat())
    # One merchant whose trial ends in 3 days (expiring soon).
    _u, _t, c_trial = await make_client_under_agent(client, agent_id)
    soon = (now + timedelta(days=3)).date().isoformat()
    await _set_client(c_trial, created_at=now - timedelta(days=1),
                      subscription_status="trialing", trial_end=soon)

    # A settled subscription payment (revenue trend, current month).
    async with db_manager.async_session_maker() as db:
        db.add(Subscription_payments(
            user_id="u", client_id=c_new1, amount=100.0, method="manual",
            created_at=now,
        ))
        await db.commit()

    resp = await client.get(
        "/api/v1/tenant/agent/dashboard-kpis", headers=auth_headers(a_token)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Active merchants: c_new1, c_new2, c_old, c_trial = 4 (excludes suspended + archived).
    assert body["active_merchants"] == 4
    # Growth: 4 non-archived created in last 30d (new1, new2, susp, trial); arch excluded.
    assert body["merchant_growth"]["new_current"] == 4
    # The 45-day-old merchant falls in the prior 30-day window.
    assert body["merchant_growth"]["new_previous"] == 1
    assert body["merchant_growth"]["delta"] == 3
    # Trial expiry: one merchant expiring within the window, soonest stamped.
    assert body["trial_expiry"]["expiring_soon"] == 1
    assert body["trial_expiry"]["next_trial_end"] == soon
    # Revenue trend has at least the current month with the settled 100.
    assert isinstance(body["revenue_trend"], list)
    assert sum(p["amount"] for p in body["revenue_trend"]) == 100.0


@pytest.mark.asyncio
async def test_agent_dashboard_kpis_is_agent_only(client):
    _mu, m_token = await make_master_account(client)
    denied = await client.get(
        "/api/v1/tenant/agent/dashboard-kpis", headers=auth_headers(m_token)
    )
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_agent_dashboard_kpis_scoped_to_owner(client):
    """One agent never sees another agent's merchants in the KPI counts."""
    _a1u, a1_token, agent1 = await make_agent_account(client)
    _a2u, _a2t, agent2 = await make_agent_account(client)
    # agent2 owns two active merchants; agent1 owns none.
    for _ in range(2):
        _u, _t, cid = await make_client_under_agent(client, agent2)
        await _set_client(cid, subscription_status="active")

    body = (
        await client.get(
            "/api/v1/tenant/agent/dashboard-kpis", headers=auth_headers(a1_token)
        )
    ).json()
    assert body["active_merchants"] == 0
