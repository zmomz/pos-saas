"""FIN-04: idempotent recurring billing charges.

Two defects let a single billing period be charged twice:

* the per-period Moyasar idempotency key was assembled into the charge metadata
  but **dropped before the gateway request** — Moyasar never saw it, so a retried
  request created a second payment; and
* there was no DB uniqueness on the settled billing period, so a double-click or a
  scheduler-vs-manual race could record (and charge) the same period twice.

These tests drive the fix one behavior at a time: the key now rides the Moyasar
request body, a unique per-period key backs the payment ledgers, and a second
settlement of the same period reconciles to the first instead of charging again.
"""
import uuid

import httpx
import pytest
from sqlalchemy import delete, func, select, update

from conftest import auth_headers, make_agent_account, make_client_under_agent
from core.database import db_manager
from models.agent_quota_payments import Agent_quota_payments
from models.agents import Agents
from models.subscription_payments import Subscription_payments
from services.payment_gateway import MoyasarGateway


@pytest.fixture(autouse=True)
async def _purge_payments_created_here():
    """The shared test DB has no per-test isolation (TST-04/#172), so the settled
    subscription / quota payments these tests record would otherwise leak into the
    platform-wide rollups — e.g. ``test_phase6_master_economics`` (which sorts after
    this file) asserts ``platform_revenue == 0``. Delete only the payment rows each
    test inserts (id beyond the pre-test high-water mark) on the way out."""
    async with db_manager.async_session_maker() as db:
        sub_max = (await db.execute(select(func.max(Subscription_payments.id)))).scalar() or 0
        quota_max = (await db.execute(select(func.max(Agent_quota_payments.id)))).scalar() or 0
    yield
    async with db_manager.async_session_maker() as db:
        await db.execute(delete(Subscription_payments).where(Subscription_payments.id > sub_max))
        await db.execute(delete(Agent_quota_payments).where(Agent_quota_payments.id > quota_max))
        await db.commit()


# ---------------------------------------------------------------------------
# A minimal fake httpx client that captures the outbound Moyasar request body
# so we can assert the idempotency key was actually transported (no network).
# ---------------------------------------------------------------------------
class _FakeResp:
    status_code = 200
    content = b"{}"

    def json(self):
        return {
            "id": "pay_fin04",
            "status": "paid",
            "source": {"company": "visa", "number": "xxxxxxxxxxxx4242"},
        }


class _CapturingClient:
    captured: dict = {}

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None, auth=None):
        _CapturingClient.captured = {"url": url, "json": json, "auth": auth}
        return _FakeResp()


@pytest.mark.asyncio
async def test_moyasar_charge_transports_idempotency_key(monkeypatch):
    """AC#1: the per-period idempotency key reaches the Moyasar request body."""
    monkeypatch.setattr(httpx, "AsyncClient", _CapturingClient)
    _CapturingClient.captured = {}

    gateway = MoyasarGateway("sk_test_fin04")
    result = await gateway.charge(
        amount=99.0,
        tender_type="card",
        token="tok_card_on_file",
        metadata={
            "recurring": True,
            "description": "Subscription (client 1)",
            "client_id": "1",
            "idempotency_key": "sub-1-2026-06-26",
        },
    )

    assert result.approved is True
    payload = _CapturingClient.captured["json"]
    # The key must ride the actual request, not be dropped before it.
    assert payload.get("metadata", {}).get("idempotency_key") == "sub-1-2026-06-26"


@pytest.mark.asyncio
async def test_period_unique_constraint_rejects_second_settlement(client):
    """AC#2 (DB backstop): a second settlement for the same (client, period_key)
    raw insert is rejected by the database — the period is the arbiter."""
    from sqlalchemy.exc import IntegrityError

    _u, _t, agent_id = await make_agent_account(client)
    _u2, _t2, client_id = await make_client_under_agent(client, agent_id)
    period_key = f"2026-06-26-{uuid.uuid4().hex[:8]}"

    async with db_manager.async_session_maker() as db:
        db.add(
            Subscription_payments(
                user_id="u",
                client_id=client_id,
                amount=10,
                billing_cycle="monthly",
                period_start="2026-06-26",
                period_end="2026-07-26",
                method="sandbox",
                reference="ref_1",
                period_key=period_key,
            )
        )
        await db.commit()

    with pytest.raises(IntegrityError):
        async with db_manager.async_session_maker() as db:
            db.add(
                Subscription_payments(
                    user_id="u",
                    client_id=client_id,
                    amount=10,
                    billing_cycle="monthly",
                    period_start="2026-06-26",
                    period_end="2026-07-26",
                    method="sandbox",
                    reference="ref_2",
                    period_key=period_key,
                )
            )
            await db.commit()


@pytest.mark.asyncio
async def test_double_pay_settles_one_charge(client):
    """AC#2 (end-to-end): a double-click on subscription/pay charges once. The
    second call reconciles to the period already settled, recording no second
    payment and re-charging nothing."""
    _u, agent_token, agent_id = await make_agent_account(client)
    _u2, client_token, client_id = await make_client_under_agent(client, agent_id)

    resp = await client.put(
        f"/api/v1/tenant/agent/clients/{client_id}/subscription",
        json={"subscription_fee": 50.0, "billing_cycle": "monthly"},
        headers=auth_headers(agent_token),
    )
    assert resp.status_code == 200, resp.text

    r1 = await client.post(
        "/api/v1/tenant/client/subscription/pay", headers=auth_headers(client_token)
    )
    assert r1.status_code == 200, r1.text
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
    assert len(settled) == 1, f"expected one settled charge, got {len(settled)}"
    assert settled[0].period_key  # the settled-period key was stamped


@pytest.mark.asyncio
async def test_double_quota_pay_settles_one_charge(client):
    """AC#2 (quota rail): a double-click on quota/pay charges the agent once."""
    _user, agent_token, agent_id = await make_agent_account(client)
    async with db_manager.async_session_maker() as db:
        await db.execute(
            update(Agents)
            .where(Agents.id == agent_id)
            .values(quota_price=100.0, quota_cycle="monthly")
        )
        await db.commit()

    r1 = await client.post("/api/v1/tenant/agent/quota/pay", headers=auth_headers(agent_token))
    assert r1.status_code == 200, r1.text
    r2 = await client.post("/api/v1/tenant/agent/quota/pay", headers=auth_headers(agent_token))
    assert r2.status_code == 200, r2.text

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
