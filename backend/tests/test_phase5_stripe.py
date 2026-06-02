"""Phase 5 (deferred): Stripe-Connect subscription charge + auto-suspend webhook.

Stripe is not configured in the test environment, so the pay path fails open to a
manual settled record (preserving prior behaviour) while the webhook drives the
non-payment auto-suspend (CL-05) and recovery re-activation.
"""
import pytest
from sqlalchemy import select

from conftest import (
    auth_headers,
    make_agent_account,
    make_client_under_agent,
)
from core.database import db_manager
from models.clients import Clients
from models.subscription_payments import Subscription_payments
from services.subscription_billing import ChargeResult, charge_subscription


@pytest.mark.asyncio
async def test_charge_subscription_manual_when_stripe_unconfigured(monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    result = await charge_subscription(amount=99.0, client_id=1)
    assert isinstance(result, ChargeResult)
    assert result.charged is False
    assert result.method == "manual"
    assert result.reference is None


@pytest.mark.asyncio
async def test_pay_records_manual_when_stripe_unconfigured(client):
    agent_user, agent_token, agent_id = await make_agent_account(client)
    client_user, client_token, client_id = await make_client_under_agent(client, agent_id)

    # Agent sets a fee.
    resp = await client.put(
        f"/api/v1/tenant/agent/clients/{client_id}/subscription",
        json={"subscription_fee": 50.0, "billing_cycle": "monthly"},
        headers=auth_headers(agent_token),
    )
    assert resp.status_code == 200, resp.text

    # Client pays — manual settlement (no Stripe).
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
    assert pay.method == "manual"


@pytest.mark.asyncio
async def test_webhook_payment_failed_suspends_client(client):
    agent_user, agent_token, agent_id = await make_agent_account(client)
    client_user, client_token, client_id = await make_client_under_agent(client, agent_id)

    # Client can authenticate before suspension.
    assert (await client.get("/api/v1/tenant/role", headers=auth_headers(client_token))).status_code == 200

    # Stripe posts a failed-payment webhook (no secret configured → JSON parsed).
    resp = await client.post(
        "/api/v1/tenant/billing/webhook",
        json={
            "type": "invoice.payment_failed",
            "data": {"object": {"metadata": {"client_id": str(client_id)}}},
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
async def test_webhook_recovery_reactivates_client(client):
    agent_user, agent_token, agent_id = await make_agent_account(client)
    client_user, client_token, client_id = await make_client_under_agent(client, agent_id)

    # Suspend, then recover.
    await client.post(
        "/api/v1/tenant/billing/webhook",
        json={
            "type": "charge.failed",
            "data": {"object": {"metadata": {"client_id": str(client_id)}}},
        },
    )
    resp = await client.post(
        "/api/v1/tenant/billing/webhook",
        json={
            "type": "payment_intent.succeeded",
            "data": {"object": {"metadata": {"client_id": str(client_id)}}},
        },
    )
    assert resp.status_code == 200
    assert resp.json()["action"] == "reactivated"

    async with db_manager.async_session_maker() as db:
        merchant = (
            await db.execute(select(Clients).where(Clients.id == client_id))
        ).scalar_one()
    assert merchant.is_active is True
    assert merchant.subscription_status == "active"


@pytest.mark.asyncio
async def test_webhook_ignores_unknown_event(client):
    resp = await client.post(
        "/api/v1/tenant/billing/webhook",
        json={"type": "customer.created", "data": {"object": {"metadata": {"client_id": "1"}}}},
    )
    assert resp.status_code == 200
    assert resp.json()["action"] == "ignored"
