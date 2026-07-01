"""ISSUE-225 (M10 Admin) — operator tenant migration (admin-console slice).

The final end-to-end slice of the operator admin console (after maintenance mode,
the feature-flag console, the job/queue monitor and the log viewers): a platform
**master** can migrate any tenant (a merchant ``Clients`` row) from one owning
agent to another from the admin console, and the state moved is real:

- the client's owning ``agent_id`` is reassigned to the destination agent;
- slots move with the merchant — a slot is atomically acquired on the destination
  first (fail closed if that agent is full, never oversold) and freed on the
  source — mirroring the agent self-serve transfer's accounting;
- a non-master tenant cannot migrate anyone (403);
- unknown client / unknown destination / same-agent / suspended-agent / full-agent
  are each refused with a specific status rather than silently corrupting state.

Distinct from ``/api/v1/tenant/agent/clients/{id}/transfer`` (agent-scoped, moves
only the caller's *own* merchant): this is the operator control plane — the master
is not an owning agent and can move *any* tenant between *any* two agents.
"""
import pytest

from conftest import (
    auth_headers,
    db_manager,
    make_agent_account,
    make_client_account,
    make_client_under_agent,
    make_master_account,
)
from models.agents import Agents
from models.clients import Clients


async def _set_agent_slots(agent_id: int, *, package_type: int, used_slots: int) -> None:
    from sqlalchemy import update

    async with db_manager.async_session_maker() as db:
        await db.execute(
            update(Agents)
            .where(Agents.id == agent_id)
            .values(package_type=package_type, used_slots=used_slots)
        )
        await db.commit()


async def _agent_used_slots(agent_id: int) -> int:
    from sqlalchemy import select

    async with db_manager.async_session_maker() as db:
        return (
            await db.execute(select(Agents.used_slots).where(Agents.id == agent_id))
        ).scalar_one()


async def _client_agent_id(client_id: int) -> int:
    from sqlalchemy import select

    async with db_manager.async_session_maker() as db:
        return (
            await db.execute(select(Clients.agent_id).where(Clients.id == client_id))
        ).scalar_one()


async def _migrate(client, headers, client_id, **body):
    return await client.post(
        f"/api/v1/admin/tenants/{client_id}/migrate", headers=headers, json=body
    )


@pytest.mark.asyncio
async def test_master_migrates_tenant_between_agents_with_slots(client):
    """Master moves a live merchant to another agent; agent_id and slots both move."""
    _master, mtoken = await make_master_account(client)
    _sa, _st, source_agent = await make_agent_account(client, package_type=5)
    _ta, _tt, target_agent = await make_agent_account(client, package_type=5)
    # The source agent holds this merchant's slot.
    await _set_agent_slots(source_agent, package_type=5, used_slots=1)
    await _set_agent_slots(target_agent, package_type=5, used_slots=0)
    _u, _t, client_id = await make_client_under_agent(client, source_agent)

    resp = await _migrate(client, auth_headers(mtoken), client_id, target_agent_id=target_agent)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["from_agent_id"] == source_agent
    assert body["to_agent_id"] == target_agent

    # The merchant now belongs to the destination agent, and slots followed it.
    assert await _client_agent_id(client_id) == target_agent
    assert await _agent_used_slots(source_agent) == 0
    assert await _agent_used_slots(target_agent) == 1


@pytest.mark.asyncio
async def test_non_master_cannot_migrate_tenant(client):
    """A tenant operator has no business migrating tenants (403)."""
    _u, token, client_id = await make_client_account(client)
    resp = await _migrate(client, auth_headers(token), client_id, target_agent_id=1)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_migrate_unknown_client_is_404(client):
    _master, mtoken = await make_master_account(client)
    _ta, _tt, target_agent = await make_agent_account(client, package_type=5)
    resp = await _migrate(client, auth_headers(mtoken), 999999, target_agent_id=target_agent)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_migrate_to_unknown_agent_is_404(client):
    _master, mtoken = await make_master_account(client)
    _sa, _st, source_agent = await make_agent_account(client, package_type=5)
    _u, _t, client_id = await make_client_under_agent(client, source_agent)
    resp = await _migrate(client, auth_headers(mtoken), client_id, target_agent_id=999999)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_migrate_to_same_agent_is_400(client):
    _master, mtoken = await make_master_account(client)
    _sa, _st, source_agent = await make_agent_account(client, package_type=5)
    _u, _t, client_id = await make_client_under_agent(client, source_agent)
    resp = await _migrate(client, auth_headers(mtoken), client_id, target_agent_id=source_agent)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_migrate_missing_target_is_400(client):
    """Neither a target id nor email supplied is a bad request."""
    _master, mtoken = await make_master_account(client)
    _sa, _st, source_agent = await make_agent_account(client, package_type=5)
    _u, _t, client_id = await make_client_under_agent(client, source_agent)
    resp = await _migrate(client, auth_headers(mtoken), client_id)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_migrate_to_full_agent_is_409_and_no_oversell(client):
    """A full destination is refused (409); no slots move, merchant stays put."""
    _master, mtoken = await make_master_account(client)
    _sa, _st, source_agent = await make_agent_account(client, package_type=5)
    _ta, _tt, target_agent = await make_agent_account(client, package_type=1)
    await _set_agent_slots(source_agent, package_type=5, used_slots=1)
    await _set_agent_slots(target_agent, package_type=1, used_slots=1)  # full
    _u, _t, client_id = await make_client_under_agent(client, source_agent)

    resp = await _migrate(client, auth_headers(mtoken), client_id, target_agent_id=target_agent)
    assert resp.status_code == 409
    # Nothing moved.
    assert await _client_agent_id(client_id) == source_agent
    assert await _agent_used_slots(source_agent) == 1
    assert await _agent_used_slots(target_agent) == 1


@pytest.mark.asyncio
async def test_migrate_to_suspended_agent_is_409(client):
    _master, mtoken = await make_master_account(client)
    _sa, _st, source_agent = await make_agent_account(client, package_type=5)
    _ta, _tt, target_agent = await make_agent_account(client, package_type=5)
    async with db_manager.async_session_maker() as db:
        from sqlalchemy import update

        await db.execute(update(Agents).where(Agents.id == target_agent).values(is_active=False))
        await db.commit()
    _u, _t, client_id = await make_client_under_agent(client, source_agent)
    resp = await _migrate(client, auth_headers(mtoken), client_id, target_agent_id=target_agent)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_master_migrates_by_target_agent_email(client):
    """The destination can be addressed by email as well as id."""
    _master, mtoken = await make_master_account(client)
    _sa, _st, source_agent = await make_agent_account(client, package_type=5)
    _ta, _tt, target_agent = await make_agent_account(client, package_type=5)
    await _set_agent_slots(source_agent, package_type=5, used_slots=1)
    _u, _t, client_id = await make_client_under_agent(client, source_agent)

    async with db_manager.async_session_maker() as db:
        from sqlalchemy import select

        target_email = (
            await db.execute(select(Agents.email).where(Agents.id == target_agent))
        ).scalar_one()

    resp = await _migrate(
        client, auth_headers(mtoken), client_id, target_agent_email=target_email
    )
    assert resp.status_code == 200, resp.text
    assert await _client_agent_id(client_id) == target_agent
