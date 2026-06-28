"""ARC-05 — pin the single, documented tenant boundary.

ARC-05 (#162) added ``client_id`` to six entities. Issue #193 flagged that the
"client_id scoping" framing overstated what is enforced: isolation is, and stays,
bounded by ``owner_user_id`` (the tenancy owner's ``user_id``). ``client_id`` is
*advisory* — denormalised metadata stamped for parity with the core tables and
usable only as a within-tenant narrowing filter, never an isolation boundary.

These tests make that decision executable so reads, writes, and the migration
backfill provably agree on one boundary:

1. The read boundary is ``user_id`` even when ``client_id`` is ``None`` — an
   account with no ``clients`` row still isolates correctly, proving ``client_id``
   is not what isolates.
2. ``resolve_tenant_scope`` (which writes stamp ``scope.client_id`` from) resolves
   to the *lowest-id* ``clients`` row for a ``user_id`` — the exact owner the
   ARC-05 migration backfill picks (``ORDER BY c.id ASC LIMIT 1``). So a row's
   stamped ``client_id`` and its backfilled ``client_id`` can never diverge.

One behaviour per test.
"""
import uuid

import pytest
from sqlalchemy import select

from core.database import db_manager
from dependencies.tenancy import resolve_tenant_scope
from models.agents import Agents
from models.clients import Clients
from schemas.auth import UserResponse

from conftest import auth_headers, make_client_account, unique_email


async def _register_plain_user(client):
    """Register a login with no ``clients`` row (so its scope's client_id is None)."""
    email = unique_email()
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123", "name": "Plain User"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["user"], body["token"]


@pytest.mark.asyncio
async def test_read_boundary_is_user_id_even_when_client_id_is_none(client):
    """An account with no ``clients`` row (client_id resolves to None) still
    isolates its own rows from another such account — proving ``user_id``, not
    ``client_id``, is the tenant boundary."""
    user_a, token_a = await _register_plain_user(client)
    user_b, token_b = await _register_plain_user(client)

    created = await client.post(
        "/api/v1/entities/categories",
        headers=auth_headers(token_a),
        json={"name": "A-only, no client row"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    # client_id is advisory: with no owning client it is simply unset.
    assert body["client_id"] is None

    # A reads its own row back...
    own = await client.get(
        "/api/v1/entities/categories", headers=auth_headers(token_a)
    )
    assert own.status_code == 200, own.text
    assert any(item["id"] == body["id"] for item in own.json()["items"])

    # ...while B (also client_id None) cannot see it. Isolation holds on user_id
    # alone, with client_id None on both sides.
    other = await client.get(
        "/api/v1/entities/categories", headers=auth_headers(token_b)
    )
    assert other.status_code == 200, other.text
    assert all(item["id"] != body["id"] for item in other.json()["items"])


@pytest.mark.asyncio
async def test_scope_resolves_lowest_id_client_matching_backfill(client):
    """When a ``user_id`` owns more than one ``clients`` row, the resolved scope's
    ``client_id`` is the lowest id — the same owner the ARC-05 migration backfill
    selects — so a stamped ``client_id`` and a backfilled one never diverge."""
    user, token, first_client_id = await make_client_account(client)

    # Drift: a second clients row for the same user with a strictly higher id.
    async with db_manager.async_session_maker() as db:
        agent = Agents(
            user_id=str(uuid.uuid4()),
            company_name="Second Agent",
            email=unique_email(),
            package_type=1,
            used_slots=0,
            is_active=True,
        )
        db.add(agent)
        await db.commit()
        await db.refresh(agent)

        second = Clients(
            user_id=user["id"],
            agent_id=agent.id,
            business_name="Second Shop",
            email=unique_email(),
            is_active=True,
            business_type="retail",
            invoice_counter=0,
        )
        db.add(second)
        await db.commit()
        await db.refresh(second)

    assert second.id > first_client_id  # sanity: the drift row is higher-id

    pseudo = UserResponse(id=user["id"], email=user.get("email", ""), name="X", role="user")
    async with db_manager.async_session_maker() as db:
        scope = await resolve_tenant_scope(db, pseudo)

    # The resolver mirrors the migration backfill: lowest-id client wins.
    assert scope.owner_user_id == user["id"]
    assert scope.client_id == first_client_id
