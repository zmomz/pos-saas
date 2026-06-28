"""SEC-02: agent quota-suspension (Agents.is_active=False) enforced at auth (#184).

The quota dunning sweep sets ``Agents.is_active=False`` / ``quota_status='suspended'``
when an agent fails to pay for his slot quota. That suspension must take effect at
the auth layer: the agent himself AND every merchant provisioned under him go dark
(cascade), while unaffected agents and their merchants are untouched.
"""
from sqlalchemy import update

from conftest import (
    auth_headers,
    make_agent_account,
    make_client_under_agent,
)
from core.database import db_manager
from models.agents import Agents


async def _suspend_agent(agent_id: int) -> None:
    async with db_manager.async_session_maker() as db:
        await db.execute(
            update(Agents).where(Agents.id == agent_id).values(
                is_active=False, quota_status="suspended"
            )
        )
        await db.commit()


async def test_active_agent_can_authenticate(client):
    _, token, _ = await make_agent_account(client)
    resp = await client.get("/api/v1/auth/me", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text


async def test_suspended_agent_self_login_blocked(client):
    _, token, agent_id = await make_agent_account(client)
    await _suspend_agent(agent_id)
    resp = await client.get("/api/v1/auth/me", headers=auth_headers(token))
    assert resp.status_code == 403, resp.text
    assert "suspended" in resp.json()["detail"].lower()


async def test_suspended_agent_cascades_to_his_merchant(client):
    _, _, agent_id = await make_agent_account(client)
    _, merchant_token, _ = await make_client_under_agent(client, agent_id)

    # Merchant authenticates fine while the agent is active.
    ok = await client.get("/api/v1/auth/me", headers=auth_headers(merchant_token))
    assert ok.status_code == 200, ok.text

    await _suspend_agent(agent_id)

    blocked = await client.get("/api/v1/auth/me", headers=auth_headers(merchant_token))
    assert blocked.status_code == 403, blocked.text
    assert "suspended" in blocked.json()["detail"].lower()


async def test_unaffected_agent_and_merchant_untouched(client):
    # Suspend one agent; an unrelated agent and its merchant keep working.
    _, _, suspended_agent_id = await make_agent_account(client)
    await _suspend_agent(suspended_agent_id)

    _, other_agent_token, other_agent_id = await make_agent_account(client)
    _, other_merchant_token, _ = await make_client_under_agent(client, other_agent_id)

    agent_resp = await client.get("/api/v1/auth/me", headers=auth_headers(other_agent_token))
    assert agent_resp.status_code == 200, agent_resp.text
    merchant_resp = await client.get(
        "/api/v1/auth/me", headers=auth_headers(other_merchant_token)
    )
    assert merchant_resp.status_code == 200, merchant_resp.text
