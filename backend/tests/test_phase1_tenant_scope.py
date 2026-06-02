"""Phase 1 (deferred): deep get_tenant_scope tenancy refactor.

Proves the centralised tenancy boundary:
* a client merchant resolves to its own user_id (+ client_id / agent_id),
* an agent resolves to its agent_id,
* the platform master is unrestricted (owner_user_id is None),
* a staff member resolves to the *owning* client's user_id (shared catalog),
* cross-tenant product reads are blocked while master sees everything.
"""
import uuid

import pytest

from core.database import db_manager
from dependencies.tenancy import resolve_tenant_scope
from schemas.auth import UserResponse
from models.staff_members import Staff_members

from conftest import (
    add_product,
    auth_headers,
    make_agent_account,
    make_client_account,
    make_master_account,
    unique_email,
)


def _as_user(user: dict) -> UserResponse:
    return UserResponse(id=user["id"], email=user.get("email", ""), name="X", role="user")


@pytest.mark.asyncio
async def test_scope_resolves_client(client):
    user, _token, client_id = await make_client_account(client)
    async with db_manager.async_session_maker() as db:
        scope = await resolve_tenant_scope(db, _as_user(user))
    assert scope.role == "client"
    assert scope.owner_user_id == user["id"]
    assert scope.client_id == client_id
    assert scope.is_unrestricted is False


@pytest.mark.asyncio
async def test_scope_resolves_agent(client):
    user, _token, agent_id = await make_agent_account(client)
    async with db_manager.async_session_maker() as db:
        scope = await resolve_tenant_scope(db, _as_user(user))
    assert scope.role == "agent"
    assert scope.agent_id == agent_id
    assert scope.owner_user_id == user["id"]


@pytest.mark.asyncio
async def test_scope_resolves_master_unrestricted(client):
    user, _token = await make_master_account(client)
    async with db_manager.async_session_maker() as db:
        scope = await resolve_tenant_scope(db, _as_user(user))
    assert scope.role == "master"
    assert scope.owner_user_id is None
    assert scope.is_unrestricted is True


@pytest.mark.asyncio
async def test_staff_member_resolves_to_owning_client(client):
    """A cashier (separate login) attached to a merchant shares the merchant's tenant."""
    owner, _token, owner_client_id = await make_client_account(client)
    staff_email = unique_email()
    staff_user, _t2, _r = None, None, None
    # Register the cashier's own login.
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": staff_email, "password": "Password123", "name": "Cashier"},
    )
    assert resp.status_code == 201
    staff_login = resp.json()["user"]

    # Link a staff row (owned by the merchant's user_id) keyed on the cashier email.
    async with db_manager.async_session_maker() as db:
        db.add(
            Staff_members(
                user_id=owner["id"],
                name="Cashier",
                email=staff_email,
                role="cashier",
                is_active=True,
            )
        )
        await db.commit()

    async with db_manager.async_session_maker() as db:
        scope = await resolve_tenant_scope(
            db, UserResponse(id=staff_login["id"], email=staff_email, name="Cashier", role="user")
        )
    # The cashier's *own* id differs, but the tenancy owner is the merchant.
    assert scope.role == "client"
    assert scope.owner_user_id == owner["id"]
    assert scope.client_id == owner_client_id


@pytest.mark.asyncio
async def test_cross_tenant_product_read_blocked(client):
    user_a, token_a, client_a = await make_client_account(client)
    user_b, token_b, _client_b = await make_client_account(client)
    pid = await add_product(client_a, user_a["id"], name="A-only")

    # B cannot read A's product directly.
    resp = await client.get(f"/api/v1/entities/products/{pid}", headers=auth_headers(token_b))
    assert resp.status_code == 404

    # B's list does not include A's product.
    resp = await client.get("/api/v1/entities/products", headers=auth_headers(token_b))
    assert resp.status_code == 200
    names = [p["name"] for p in resp.json()["items"]]
    assert "A-only" not in names

    # A can read its own.
    resp = await client.get(f"/api/v1/entities/products/{pid}", headers=auth_headers(token_a))
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_master_sees_all_products(client):
    user_a, _ta, client_a = await make_client_account(client)
    await add_product(client_a, user_a["id"], name=f"master-vis-{uuid.uuid4().hex[:6]}")
    master_user, master_token = await make_master_account(client)

    resp = await client.get(
        "/api/v1/entities/products?limit=2000", headers=auth_headers(master_token)
    )
    assert resp.status_code == 200
    # Master is unrestricted: it sees products it does not own.
    owners = {p["user_id"] for p in resp.json()["items"]}
    assert any(o != master_user["id"] for o in owners)
