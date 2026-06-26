"""Moyasar subscription billing (Rail 2) + auto-suspend webhooks.

The merchant subscription charge routes through the owning agent's own Moyasar
account against the merchant's stored card-on-file. With no Moyasar keys configured
(the test environment) the deterministic sandbox gateway settles the charge so the
flow is demonstrable without onboarding (OPS-08). A real agent key with no card on
file fails closed (no silent free pass). The per-agent webhook drives the
non-payment auto-suspend and recovery re-activation.
"""
import pytest
from sqlalchemy import select, update

from conftest import auth_headers, make_agent_account, make_client_under_agent
from core.database import db_manager
from models.agents import Agents
from models.clients import Clients
from models.subscription_payments import Subscription_payments
from services.subscription_billing import ChargeResult, SubscriptionChargeError, charge_subscription


@pytest.mark.asyncio
async def test_charge_settles_via_sandbox_when_no_keys_configured(monkeypatch):
    monkeypatch.delenv("MOYASAR_API_KEY", raising=False)
    result = await charge_subscription(amount=99.0, client_id=1)
    assert isinstance(result, ChargeResult)
    assert result.charged is True
    assert result.method == "sandbox"
    assert result.reference  # a synthesized sandbox reference


@pytest.mark.asyncio
async def test_charge_fails_closed_with_agent_key_but_no_card(monkeypatch):
    monkeypatch.delenv("MOYASAR_API_KEY", raising=False)
    # A real agent account is configured but the merchant has no card on file:
    # the charge must fail closed (402), never silently succeed for free.
    with pytest.raises(SubscriptionChargeError):
        await charge_subscription(
            amount=99.0, client_id=1, agent_moyasar_key="sk_live_agent", card_token=None
        )


@pytest.mark.asyncio
async def test_pay_records_payment(client):
    _agent_user, agent_token, agent_id = await make_agent_account(client)
    _client_user, client_token, client_id = await make_client_under_agent(client, agent_id)

    resp = await client.put(
        f"/api/v1/tenant/agent/clients/{client_id}/subscription",
        json={"subscription_fee": 50.0, "billing_cycle": "monthly"},
        headers=auth_headers(agent_token),
    )
    assert resp.status_code == 200, resp.text

    resp = await client.post(
        "/api/v1/tenant/client/subscription/pay", headers=auth_headers(client_token)
    )
    assert resp.status_code == 200, resp.text

    async with db_manager.async_session_maker() as db:
        pay = (
            await db.execute(
                select(Subscription_payments).where(Subscription_payments.client_id == client_id)
            )
        ).scalars().first()
    assert pay is not None
    assert pay.amount == 50.0
    assert pay.method in ("moyasar", "sandbox")


@pytest.mark.asyncio
async def test_merchant_webhook_payment_failed_suspends_client(client):
    _agent_user, _agent_token, agent_id = await make_agent_account(client)
    _client_user, client_token, client_id = await make_client_under_agent(client, agent_id)

    # Client can authenticate before suspension.
    assert (await client.get("/api/v1/tenant/role", headers=auth_headers(client_token))).status_code == 200

    # The agent's Moyasar posts a failed-payment webhook (no secret configured on
    # the agent → body trusted in dev/test).
    resp = await client.post(
        f"/api/v1/tenant/billing/webhook/agent/{agent_id}",
        json={
            "type": "payment_failed",
            "data": {"metadata": {"client_id": str(client_id)}},
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["action"] == "suspended"

    async with db_manager.async_session_maker() as db:
        merchant = (
            await db.execute(select(Clients).where(Clients.id == client_id))
        ).scalar_one()
    assert merchant.is_active is False
    assert merchant.subscription_status == "suspended"

    # The suspended client is now blocked at authentication.
    blocked = await client.get("/api/v1/tenant/role", headers=auth_headers(client_token))
    assert blocked.status_code == 403


@pytest.mark.asyncio
async def test_merchant_webhook_recovery_reactivates_client(client):
    _agent_user, _agent_token, agent_id = await make_agent_account(client)
    _client_user, _client_token, client_id = await make_client_under_agent(client, agent_id)
    async with db_manager.async_session_maker() as db:
        await db.execute(
            update(Clients)
            .where(Clients.id == client_id)
            .values(is_active=False, subscription_status="suspended")
        )
        await db.commit()

    resp = await client.post(
        f"/api/v1/tenant/billing/webhook/agent/{agent_id}",
        json={"type": "payment_paid", "data": {"metadata": {"client_id": str(client_id)}}},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["action"] == "reactivated"


@pytest.mark.asyncio
async def test_merchant_webhook_ignores_client_of_other_agent(client):
    _a1u, _a1t, agent1 = await make_agent_account(client)
    _a2u, _a2t, agent2 = await make_agent_account(client)
    _cu, _ct, client_of_a1 = await make_client_under_agent(client, agent1)

    # Agent2's webhook must not be able to suspend agent1's client.
    resp = await client.post(
        f"/api/v1/tenant/billing/webhook/agent/{agent2}",
        json={"type": "payment_failed", "data": {"metadata": {"client_id": str(client_of_a1)}}},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["action"] == "ignored"


@pytest.mark.asyncio
async def test_quota_webhook_suspends_agent(client, monkeypatch):
    import hashlib
    import hmac
    import json as _json

    from core.config import settings
    from core.webhooks import MOYASAR_SIGNATURE_HEADER

    # The platform quota webhook now requires a valid HMAC signature (SEC-02).
    secret = "whsec_quota"
    monkeypatch.setitem(settings.__dict__, "moyasar_webhook_secret", secret)
    _agent_user, _agent_token, agent_id = await make_agent_account(client)
    body = _json.dumps(
        {"id": "evt_suspend", "type": "payment_failed", "data": {"metadata": {"agent_id": str(agent_id)}}}
    ).encode()
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    resp = await client.post(
        "/api/v1/tenant/quota/webhook",
        content=body,
        headers={MOYASAR_SIGNATURE_HEADER: sig},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["action"] == "suspended"

    async with db_manager.async_session_maker() as db:
        agent = (await db.execute(select(Agents).where(Agents.id == agent_id))).scalar_one()
    assert agent.is_active is False
    assert agent.quota_status == "suspended"
