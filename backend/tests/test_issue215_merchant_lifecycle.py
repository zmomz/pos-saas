"""M8 / issue-215 — merchant lifecycle (archive / restore / transfer / export / delete).

An agent manages their merchant book beyond plain suspension: archive a merchant
without data loss (freeing its slot + blocking its login), restore it back,
transfer it to another agent (changing the owning ``agent_id``), export a portable
snapshot, and permanently delete it once its retention window has lapsed.

Maps to the issue acceptance criteria:
  * "Merchant can be archived and restored without data loss."
  * "Merchant can be transferred to another agent."
"""
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update

from conftest import (
    auth_headers,
    make_agent_account,
    make_client_under_agent,
)
from core.database import db_manager
from models.clients import Clients


async def _provision_client(client: AsyncClient, agent_token: str, email: str):
    """Provision a merchant through the real agent endpoint (deducts a slot)."""
    resp = await client.post(
        "/api/v1/tenant/agent/clients",
        headers=auth_headers(agent_token),
        json={"business_name": "Acme", "email": email, "subscription_fee": 100},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Archive + restore: data preserved, list view splits, login blocked/unblocked.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_archive_then_restore_preserves_merchant_without_data_loss(client: AsyncClient):
    _agent, agent_token, agent_id = await make_agent_account(client)
    _cl, client_token, client_id = await make_client_under_agent(client, agent_id)

    # The merchant can authenticate before archiving.
    pre = await client.get(
        "/api/v1/tenant/client/subscription", headers=auth_headers(client_token)
    )
    assert pre.status_code == 200, pre.text

    # Archive it.
    arch = await client.post(
        f"/api/v1/tenant/agent/clients/{client_id}/archive",
        headers=auth_headers(agent_token),
    )
    assert arch.status_code == 200, arch.text
    assert arch.json()["archived_at"]

    # It vanishes from the active book and appears in the archived view.
    active = await client.get(
        "/api/v1/tenant/agent/clients", headers=auth_headers(agent_token)
    )
    assert client_id not in [c["id"] for c in active.json()["items"]]
    archived = await client.get(
        "/api/v1/tenant/agent/clients?archived=true", headers=auth_headers(agent_token)
    )
    assert client_id in [c["id"] for c in archived.json()["items"]]

    # The merchant's login is now blocked (distinct archived state, 403).
    blocked = await client.get(
        "/api/v1/tenant/client/subscription", headers=auth_headers(client_token)
    )
    assert blocked.status_code == 403, blocked.text

    # The underlying row + its data are untouched (no data loss).
    async with db_manager.async_session_maker() as db:
        row = (await db.execute(select(Clients).where(Clients.id == client_id))).scalar_one()
        assert row.business_name == "Shop"
        assert row.email == _cl["email"]
        assert row.archived_at is not None

    # Restore it back into the active book.
    rest = await client.post(
        f"/api/v1/tenant/agent/clients/{client_id}/restore",
        headers=auth_headers(agent_token),
    )
    assert rest.status_code == 200, rest.text
    assert rest.json()["archived_at"] is None

    # Active again; login works again.
    active2 = await client.get(
        "/api/v1/tenant/agent/clients", headers=auth_headers(agent_token)
    )
    assert client_id in [c["id"] for c in active2.json()["items"]]
    post = await client.get(
        "/api/v1/tenant/client/subscription", headers=auth_headers(client_token)
    )
    assert post.status_code == 200, post.text


@pytest.mark.asyncio
async def test_archive_frees_a_slot_and_restore_reclaims_it(client: AsyncClient):
    # package_type=1 so the slot accounting is observable end-to-end.
    _agent, agent_token, agent_id = await make_agent_account(client, package_type=1)
    created = await _provision_client(client, agent_token, "slotmerchant@x.io")
    client_id = created["id"]

    # The single slot is now taken — a second provision fails (409).
    full = await client.post(
        "/api/v1/tenant/agent/clients",
        headers=auth_headers(agent_token),
        json={"business_name": "Second", "email": "second@x.io"},
    )
    assert full.status_code == 409

    # Archiving frees the slot.
    await client.post(
        f"/api/v1/tenant/agent/clients/{client_id}/archive",
        headers=auth_headers(agent_token),
    )
    listing = await client.get(
        "/api/v1/tenant/agent/clients", headers=auth_headers(agent_token)
    )
    assert listing.json()["remaining_slots"] == 1

    # Now a fresh merchant can be provisioned into the freed slot.
    second = await client.post(
        "/api/v1/tenant/agent/clients",
        headers=auth_headers(agent_token),
        json={"business_name": "Second", "email": "second@x.io"},
    )
    assert second.status_code == 200, second.text

    # And restoring the archived one fails closed — the package is full again (409).
    rest = await client.post(
        f"/api/v1/tenant/agent/clients/{client_id}/restore",
        headers=auth_headers(agent_token),
    )
    assert rest.status_code == 409, rest.text


@pytest.mark.asyncio
async def test_archive_is_not_double_freeable(client: AsyncClient):
    _agent, agent_token, agent_id = await make_agent_account(client)
    _cl, _ct, client_id = await make_client_under_agent(client, agent_id)
    first = await client.post(
        f"/api/v1/tenant/agent/clients/{client_id}/archive",
        headers=auth_headers(agent_token),
    )
    assert first.status_code == 200
    again = await client.post(
        f"/api/v1/tenant/agent/clients/{client_id}/archive",
        headers=auth_headers(agent_token),
    )
    assert again.status_code == 409


@pytest.mark.asyncio
async def test_restore_requires_archived(client: AsyncClient):
    _agent, agent_token, agent_id = await make_agent_account(client)
    _cl, _ct, client_id = await make_client_under_agent(client, agent_id)
    resp = await client.post(
        f"/api/v1/tenant/agent/clients/{client_id}/restore",
        headers=auth_headers(agent_token),
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Transfer to another agent (change owner).
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_transfer_moves_merchant_to_another_agent(client: AsyncClient):
    _a1, token1, agent1 = await make_agent_account(client)
    _a2, token2, agent2 = await make_agent_account(client)
    created = await _provision_client(client, token1, "transferme@x.io")
    client_id = created["id"]

    resp = await client.post(
        f"/api/v1/tenant/agent/clients/{client_id}/transfer",
        headers=auth_headers(token1),
        json={"target_agent_id": agent2},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["from_agent_id"] == agent1 and body["to_agent_id"] == agent2

    # Source agent no longer sees it; destination agent now does.
    src = await client.get("/api/v1/tenant/agent/clients", headers=auth_headers(token1))
    assert client_id not in [c["id"] for c in src.json()["items"]]
    dst = await client.get("/api/v1/tenant/agent/clients", headers=auth_headers(token2))
    assert client_id in [c["id"] for c in dst.json()["items"]]

    # The owning agent_id was actually changed on the row.
    async with db_manager.async_session_maker() as db:
        owner = (
            await db.execute(select(Clients.agent_id).where(Clients.id == client_id))
        ).scalar_one()
        assert owner == agent2


@pytest.mark.asyncio
async def test_transfer_by_target_email_resolves_destination(client: AsyncClient):
    _a1, token1, agent1 = await make_agent_account(client)
    _a2, token2, agent2 = await make_agent_account(client)
    _cl, _ct, client_id = await make_client_under_agent(client, agent1)

    # Resolve the destination agent by its email (the handle the agent UI exposes).
    async with db_manager.async_session_maker() as db:
        from models.agents import Agents

        target_email = (
            await db.execute(select(Agents.email).where(Agents.id == agent2))
        ).scalar_one()

    resp = await client.post(
        f"/api/v1/tenant/agent/clients/{client_id}/transfer",
        headers=auth_headers(token1),
        json={"target_agent_email": target_email},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["to_agent_id"] == agent2
    dst = await client.get("/api/v1/tenant/agent/clients", headers=auth_headers(token2))
    assert client_id in [c["id"] for c in dst.json()["items"]]


@pytest.mark.asyncio
async def test_transfer_rejects_unknown_and_self_target(client: AsyncClient):
    _a1, token1, agent1 = await make_agent_account(client)
    _cl, _ct, client_id = await make_client_under_agent(client, agent1)

    missing = await client.post(
        f"/api/v1/tenant/agent/clients/{client_id}/transfer",
        headers=auth_headers(token1),
        json={"target_agent_id": 999999},
    )
    assert missing.status_code == 404

    to_self = await client.post(
        f"/api/v1/tenant/agent/clients/{client_id}/transfer",
        headers=auth_headers(token1),
        json={"target_agent_id": agent1},
    )
    assert to_self.status_code == 400


@pytest.mark.asyncio
async def test_lifecycle_actions_scoped_to_owning_agent(client: AsyncClient):
    """A non-owning agent gets 404 on every lifecycle action (SEC-02)."""
    _a1, _token1, agent1 = await make_agent_account(client)
    _a2, token2, _agent2 = await make_agent_account(client)
    _cl, _ct, client_id = await make_client_under_agent(client, agent1)

    for method, suffix in [
        ("post", "/archive"),
        ("post", "/restore"),
        ("get", "/export"),
    ]:
        resp = await getattr(client, method)(
            f"/api/v1/tenant/agent/clients/{client_id}{suffix}",
            headers=auth_headers(token2),
        )
        assert resp.status_code == 404, f"{suffix}: {resp.status_code}"


# ---------------------------------------------------------------------------
# Export.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_export_returns_portable_json_snapshot(client: AsyncClient):
    _agent, agent_token, agent_id = await make_agent_account(client)
    _cl, _ct, client_id = await make_client_under_agent(client, agent_id)

    resp = await client.get(
        f"/api/v1/tenant/agent/clients/{client_id}/export",
        headers=auth_headers(agent_token),
    )
    assert resp.status_code == 200, resp.text
    assert "attachment" in resp.headers.get("content-disposition", "")
    body = resp.json()
    assert body["merchant"]["id"] == client_id
    assert body["schema"].startswith("pos-saas/merchant-export")
    assert "record_counts" in body
    assert "subscription_payments" in body
    # Secrets must never appear in the export.
    assert "moyasar_card_token_enc" not in body["merchant"]
    assert "salla_webhook_secret" not in body["merchant"]


# ---------------------------------------------------------------------------
# Post-retention delete.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_delete_requires_archive_and_retention(client: AsyncClient):
    _agent, agent_token, agent_id = await make_agent_account(client)
    _cl, _ct, client_id = await make_client_under_agent(client, agent_id)

    # Cannot delete a live merchant.
    live = await client.delete(
        f"/api/v1/tenant/agent/clients/{client_id}",
        headers=auth_headers(agent_token),
    )
    assert live.status_code == 409

    # Archive it — but the retention window has not lapsed, so delete is still 409.
    await client.post(
        f"/api/v1/tenant/agent/clients/{client_id}/archive",
        headers=auth_headers(agent_token),
    )
    too_soon = await client.delete(
        f"/api/v1/tenant/agent/clients/{client_id}",
        headers=auth_headers(agent_token),
    )
    assert too_soon.status_code == 409

    # Backdate the archive past the retention window — now delete succeeds.
    old = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
    async with db_manager.async_session_maker() as db:
        await db.execute(
            update(Clients).where(Clients.id == client_id).values(archived_at=old)
        )
        await db.commit()

    gone = await client.delete(
        f"/api/v1/tenant/agent/clients/{client_id}",
        headers=auth_headers(agent_token),
    )
    assert gone.status_code == 200, gone.text

    async with db_manager.async_session_maker() as db:
        row = (
            await db.execute(select(Clients).where(Clients.id == client_id))
        ).scalar_one_or_none()
        assert row is None
