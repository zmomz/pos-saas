"""SEC-02 — HMAC verification on the platform quota (Rail 1) webhook.

The quota webhook (POST /v1/tenant/quota/webhook) can suspend any agent (which
cascades to block his merchants). It previously verified an echoed body token and
fell *open* whenever no secret was configured, so anyone who could reach the URL
could mass-suspend agents. These tests pin the fixed contract:

* the signature is an HMAC-SHA256 of the *raw* body, read from a request header
  (never trusted from the body);
* an unsigned request, a wrong signature, or an unset server secret are all
  rejected with 401 and leave no agent suspended;
* a valid signature suspends; a redelivery of the same event id is ignored.
"""
import hashlib
import hmac
import json

import pytest
from sqlalchemy import select

from conftest import auth_headers, make_agent_account
from core.config import settings
from core.database import db_manager
from core.webhooks import MOYASAR_SIGNATURE_HEADER, verify_moyasar_signature
from models.agents import Agents

_SECRET = "whsec_test_quota_secret"


def _sign(body: bytes, secret: str = _SECRET) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


# ---------------------------------------------------------------- helper unit


def test_verify_rejects_when_secret_unset():
    body = b'{"type":"payment_failed"}'
    assert verify_moyasar_signature(body, _sign(body), None) is False
    assert verify_moyasar_signature(body, _sign(body), "") is False


def test_verify_rejects_missing_or_wrong_signature():
    body = b'{"type":"payment_failed"}'
    assert verify_moyasar_signature(body, None, _SECRET) is False
    assert verify_moyasar_signature(body, "deadbeef", _SECRET) is False


def test_verify_accepts_valid_signature_over_raw_body():
    body = b'{"type":"payment_failed","id":"evt_1"}'
    assert verify_moyasar_signature(body, _sign(body), _SECRET) is True


# ------------------------------------------------------------- endpoint contract

_QUOTA_URL = "/api/v1/tenant/quota/webhook"


def _event(agent_id, event_type="payment_failed", event_id="evt_quota_1"):
    return json.dumps(
        {"id": event_id, "type": event_type, "data": {"metadata": {"agent_id": str(agent_id)}}}
    ).encode()


async def _agent_active(agent_id) -> bool:
    async with db_manager.async_session_maker() as db:
        agent = (await db.execute(select(Agents).where(Agents.id == agent_id))).scalar_one()
    return agent.is_active


@pytest.mark.asyncio
async def test_quota_webhook_rejects_unsigned_when_secret_set(client, monkeypatch):
    monkeypatch.setitem(settings.__dict__, "moyasar_webhook_secret", _SECRET)
    _u, _t, agent_id = await make_agent_account(client)
    body = _event(agent_id)

    resp = await client.post(_QUOTA_URL, content=body)  # no signature header

    assert resp.status_code == 401, resp.text
    assert await _agent_active(agent_id) is True


@pytest.mark.asyncio
async def test_quota_webhook_rejects_wrong_signature(client, monkeypatch):
    monkeypatch.setitem(settings.__dict__, "moyasar_webhook_secret", _SECRET)
    _u, _t, agent_id = await make_agent_account(client)
    body = _event(agent_id)

    resp = await client.post(
        _QUOTA_URL, content=body, headers={MOYASAR_SIGNATURE_HEADER: "deadbeef"}
    )

    assert resp.status_code == 401, resp.text
    assert await _agent_active(agent_id) is True


@pytest.mark.asyncio
async def test_quota_webhook_fails_closed_when_secret_unset(client, monkeypatch):
    monkeypatch.delenv("MOYASAR_WEBHOOK_SECRET", raising=False)
    monkeypatch.delitem(settings.__dict__, "moyasar_webhook_secret", raising=False)
    _u, _t, agent_id = await make_agent_account(client)
    body = _event(agent_id)

    # Even a body-signed request must be rejected when no server secret exists.
    resp = await client.post(
        _QUOTA_URL, content=body, headers={MOYASAR_SIGNATURE_HEADER: _sign(body)}
    )

    assert resp.status_code == 401, resp.text
    assert await _agent_active(agent_id) is True


@pytest.mark.asyncio
async def test_quota_webhook_valid_signature_suspends(client, monkeypatch):
    monkeypatch.setitem(settings.__dict__, "moyasar_webhook_secret", _SECRET)
    _u, _t, agent_id = await make_agent_account(client)
    body = _event(agent_id, event_id="evt_quota_suspend")

    resp = await client.post(
        _QUOTA_URL, content=body, headers={MOYASAR_SIGNATURE_HEADER: _sign(body)}
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["action"] == "suspended"
    assert await _agent_active(agent_id) is False


@pytest.mark.asyncio
async def test_quota_webhook_replay_is_ignored(client, monkeypatch):
    from sqlalchemy import update

    monkeypatch.setitem(settings.__dict__, "moyasar_webhook_secret", _SECRET)
    _u, _t, agent_id = await make_agent_account(client)
    body = _event(agent_id, event_id="evt_quota_replay")
    headers = {MOYASAR_SIGNATURE_HEADER: _sign(body)}

    first = await client.post(_QUOTA_URL, content=body, headers=headers)
    assert first.status_code == 200
    assert first.json()["action"] == "suspended"

    # An operator re-activates the agent; the same event must not re-suspend.
    async with db_manager.async_session_maker() as db:
        await db.execute(update(Agents).where(Agents.id == agent_id).values(is_active=True))
        await db.commit()

    replay = await client.post(_QUOTA_URL, content=body, headers=headers)
    assert replay.status_code == 200, replay.text
    assert replay.json()["action"] == "ignored"
    assert await _agent_active(agent_id) is True
