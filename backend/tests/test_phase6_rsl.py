"""RSL-06: an agent resets the password of one of their own client merchants.

Reseller-grade support — when a merchant is locked out, the **owning** agent
issues a fresh one-time password (force-reset on next login) without the platform
master being involved. The new credential targets the merchant's own login
account, is scoped to the agent's own clients (a non-owning agent gets 404), and
records an audit row. Only clients/agents may reach the endpoint.
"""
import pytest
from sqlalchemy import select

from conftest import (
    auth_headers,
    make_agent_account,
    make_client_account,
    make_client_under_agent,
)
from core.database import db_manager
from models.audit_logs import Audit_logs
from models.auth import User


async def _login(client, email, password):
    return await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )


@pytest.mark.asyncio
async def test_agent_resets_own_client_password_forces_change(client):
    _agent_user, agent_token, agent_id = await make_agent_account(client)
    merchant_user, _merchant_token, client_id = await make_client_under_agent(
        client, agent_id
    )
    # The merchant was provisioned with the conftest default password.
    old_password = "Password123"
    merchant_email = merchant_user["email"]

    # Sanity: the merchant can log in with the original password first.
    assert (await _login(client, merchant_email, old_password)).status_code == 200

    resp = await client.post(
        f"/api/v1/tenant/agent/clients/{client_id}/reset-password",
        headers=auth_headers(agent_token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    temp_password = body["temp_password"]
    assert body["success"] is True
    assert body["must_change_password"] is True
    assert body["email"] == merchant_email
    # The plaintext password is never the stored hash and is freshly generated.
    assert temp_password and temp_password != old_password

    # The old password no longer works; the new one-time password does.
    assert (await _login(client, merchant_email, old_password)).status_code == 401
    new_login = await _login(client, merchant_email, temp_password)
    assert new_login.status_code == 200, new_login.text

    # The merchant's own account carries the force-reset flag, and only the hash
    # is stored (never the plaintext temp password).
    async with db_manager.async_session_maker() as db:
        user = (
            await db.execute(select(User).where(User.id == merchant_user["id"]))
        ).scalar_one()
        assert user.must_change_password is True
        assert user.hashed_password and user.hashed_password != temp_password

        # An audit row records who reset which client.
        audits = (
            await db.execute(
                select(Audit_logs).where(
                    Audit_logs.action == "AGENT_RESET_CLIENT_PASSWORD",
                    Audit_logs.entity_id == str(client_id),
                )
            )
        ).scalars().all()
        assert len(audits) == 1


@pytest.mark.asyncio
async def test_non_owning_agent_cannot_reset_password(client):
    # Owning agent + its client.
    _a1_user, _a1_token, agent_id = await make_agent_account(client)
    _merchant_user, _merchant_token, client_id = await make_client_under_agent(
        client, agent_id
    )
    # A different agent must not be able to reset that client's password.
    _a2_user, a2_token, _a2_id = await make_agent_account(client)

    resp = await client.post(
        f"/api/v1/tenant/agent/clients/{client_id}/reset-password",
        headers=auth_headers(a2_token),
    )
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_client_cannot_reset_password(client):
    # A client account (not an agent) is rejected with 403.
    _agent_user, _agent_token, agent_id = await make_agent_account(client)
    _merchant_user, merchant_token, client_id = await make_client_under_agent(
        client, agent_id
    )

    resp = await client.post(
        f"/api/v1/tenant/agent/clients/{client_id}/reset-password",
        headers=auth_headers(merchant_token),
    )
    assert resp.status_code == 403, resp.text
