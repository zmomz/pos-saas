"""SEC-03 — HMAC verification on the per-agent merchant (Rail 2) webhook.

The merchant webhook (POST /v1/tenant/billing/webhook/agent/{agent_id}) can
suspend any merchant under an agent. It previously fell *open* whenever the agent
had no secret configured and compared an echoed body ``secret_token`` with ``!=``,
so anyone who could reach the URL could suspend merchants. These tests pin the
fixed contract, mirroring SEC-02 (#107):

* the signature is an HMAC-SHA256 of the *raw* body, read from a request header
  (never the echoed body token);
* an unsigned request, a wrong signature, or an agent without a configured secret
  are all rejected with 401 and leave the merchant active;
* a valid signature suspends/recovers; a redelivery of the same event id is a no-op.
"""
import hashlib
import hmac
import json

import pytest
from sqlalchemy import select, update

from conftest import make_agent_account, make_client_under_agent
from core.crypto import encrypt_secret
from core.database import db_manager
from core.webhooks import MOYASAR_SIGNATURE_HEADER
from models.agents import Agents
from models.clients import Clients

_SECRET = "whsec_test_merchant_secret"


def _sign(body: bytes, secret: str = _SECRET) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _url(agent_id) -> str:
    return f"/api/v1/tenant/billing/webhook/agent/{agent_id}"


def _event(client_id, event_type="payment_failed", event_id="evt_merch_1"):
    return json.dumps(
        {"id": event_id, "type": event_type, "data": {"metadata": {"client_id": str(client_id)}}}
    ).encode()


async def _set_agent_secret(agent_id, secret: str = _SECRET):
    async with db_manager.async_session_maker() as db:
        await db.execute(
            update(Agents)
            .where(Agents.id == agent_id)
            .values(moyasar_webhook_secret_enc=encrypt_secret(secret))
        )
        await db.commit()


async def _client_active(client_id) -> bool:
    async with db_manager.async_session_maker() as db:
        merchant = (
            await db.execute(select(Clients).where(Clients.id == client_id))
        ).scalar_one()
    return merchant.is_active


@pytest.mark.asyncio
async def test_merchant_webhook_fails_closed_when_agent_has_no_secret(client):
    _au, _at, agent_id = await make_agent_account(client)
    _cu, _ct, client_id = await make_client_under_agent(client, agent_id)
    body = _event(client_id)

    # Even a "signed" request must be rejected when the agent configured no secret.
    resp = await client.post(_url(agent_id), content=body, headers={MOYASAR_SIGNATURE_HEADER: _sign(body)})

    assert resp.status_code == 401, resp.text
    assert await _client_active(client_id) is True


@pytest.mark.asyncio
async def test_merchant_webhook_rejects_unsigned_when_secret_set(client):
    _au, _at, agent_id = await make_agent_account(client)
    _cu, _ct, client_id = await make_client_under_agent(client, agent_id)
    await _set_agent_secret(agent_id)
    body = _event(client_id)

    resp = await client.post(_url(agent_id), content=body)  # no signature header

    assert resp.status_code == 401, resp.text
    assert await _client_active(client_id) is True


@pytest.mark.asyncio
async def test_merchant_webhook_rejects_wrong_signature(client):
    _au, _at, agent_id = await make_agent_account(client)
    _cu, _ct, client_id = await make_client_under_agent(client, agent_id)
    await _set_agent_secret(agent_id)
    body = _event(client_id)

    resp = await client.post(_url(agent_id), content=body, headers={MOYASAR_SIGNATURE_HEADER: "deadbeef"})

    assert resp.status_code == 401, resp.text
    assert await _client_active(client_id) is True


@pytest.mark.asyncio
async def test_merchant_webhook_rejects_signature_from_other_agents_secret(client):
    _au, _at, agent_id = await make_agent_account(client)
    _cu, _ct, client_id = await make_client_under_agent(client, agent_id)
    await _set_agent_secret(agent_id, _SECRET)
    body = _event(client_id)

    # Signed with a *different* secret than the agent's stored one.
    resp = await client.post(
        _url(agent_id), content=body, headers={MOYASAR_SIGNATURE_HEADER: _sign(body, "whsec_other")}
    )

    assert resp.status_code == 401, resp.text
    assert await _client_active(client_id) is True


@pytest.mark.asyncio
async def test_merchant_webhook_valid_signature_suspends(client):
    _au, _at, agent_id = await make_agent_account(client)
    _cu, _ct, client_id = await make_client_under_agent(client, agent_id)
    await _set_agent_secret(agent_id)
    body = _event(client_id, event_id="evt_merch_suspend")

    resp = await client.post(_url(agent_id), content=body, headers={MOYASAR_SIGNATURE_HEADER: _sign(body)})

    assert resp.status_code == 200, resp.text
    assert resp.json()["action"] == "suspended"
    assert await _client_active(client_id) is False


@pytest.mark.asyncio
async def test_merchant_webhook_valid_signature_reactivates(client):
    _au, _at, agent_id = await make_agent_account(client)
    _cu, _ct, client_id = await make_client_under_agent(client, agent_id, is_active=False)
    await _set_agent_secret(agent_id)
    async with db_manager.async_session_maker() as db:
        await db.execute(
            update(Clients).where(Clients.id == client_id).values(subscription_status="suspended")
        )
        await db.commit()
    body = _event(client_id, event_type="payment_paid", event_id="evt_merch_recover")

    resp = await client.post(_url(agent_id), content=body, headers={MOYASAR_SIGNATURE_HEADER: _sign(body)})

    assert resp.status_code == 200, resp.text
    assert resp.json()["action"] == "reactivated"
    assert await _client_active(client_id) is True


@pytest.mark.asyncio
async def test_merchant_webhook_replay_is_ignored(client):
    _au, _at, agent_id = await make_agent_account(client)
    _cu, _ct, client_id = await make_client_under_agent(client, agent_id)
    await _set_agent_secret(agent_id)
    body = _event(client_id, event_id="evt_merch_replay")
    headers = {MOYASAR_SIGNATURE_HEADER: _sign(body)}

    first = await client.post(_url(agent_id), content=body, headers=headers)
    assert first.status_code == 200
    assert first.json()["action"] == "suspended"

    # An operator re-activates the merchant; the same event must not re-suspend.
    async with db_manager.async_session_maker() as db:
        await db.execute(update(Clients).where(Clients.id == client_id).values(is_active=True))
        await db.commit()

    replay = await client.post(_url(agent_id), content=body, headers=headers)
    assert replay.status_code == 200, replay.text
    assert replay.json()["action"] == "ignored"
    assert await _client_active(client_id) is True


@pytest.mark.asyncio
async def test_merchant_webhook_ignores_client_of_other_agent(client):
    _a1u, _a1t, agent1 = await make_agent_account(client)
    _a2u, _a2t, agent2 = await make_agent_account(client)
    _cu, _ct, client_of_a1 = await make_client_under_agent(client, agent1)
    await _set_agent_secret(agent2)  # agent2 signs with his own (valid) secret
    body = _event(client_of_a1)

    # A valid signature from agent2 still must not suspend agent1's client (SEC-02).
    resp = await client.post(_url(agent2), content=body, headers={MOYASAR_SIGNATURE_HEADER: _sign(body)})

    assert resp.status_code == 200, resp.text
    assert resp.json()["action"] == "ignored"
    assert await _client_active(client_of_a1) is True
