"""Phase 1 (deferred): deep get_tenant_scope tenancy refactor.

Proves the centralised tenancy boundary:
* a client merchant resolves to its own user_id (+ client_id / agent_id),
* an agent resolves to its agent_id,
* the platform master is unrestricted (owner_user_id is None),
* a staff member resolves to the *owning* client's user_id (shared catalog),
* cross-tenant product reads are blocked while master sees everything,
* a staff sub-user can receive their owner's PO (owner-scoped, not by login id).
"""
import json
import uuid

import pytest
from sqlalchemy import select

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


async def _make_staff_login(client, owner_user_id: str, role: str = "cashier"):
    """Register a separate login and link it as a staff member of ``owner_user_id``.

    Returns (staff_user_dict, token). The staff row is keyed on the cashier's email
    so :func:`resolve_tenant_scope` maps the cashier back to the owning merchant.
    """
    staff_email = unique_email()
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": staff_email, "password": "Password123", "name": "Cashier"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    async with db_manager.async_session_maker() as db:
        db.add(
            Staff_members(
                user_id=owner_user_id,
                name="Cashier",
                email=staff_email,
                role=role,
                is_active=True,
            )
        )
        await db.commit()
    return body["user"], body["token"]


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
async def test_staff_can_receive_owners_purchase_order(client):
    """A cashier sub-user receives a PO their owner created (no 404), cross-tenant rejected.

    Regression for H18: ``receive_purchase_order`` filtered ``Purchase_orders.user_id``
    on the *caller's* id, so a staff cashier who can list a merchant's POs got a 404
    receiving them. The receive path must scope on the owning merchant (``owner_user_id``).
    """
    owner, owner_token, client_id = await make_client_account(client)
    owner_headers = auth_headers(owner_token)
    pid = await add_product(client_id, owner["id"], quantity=0, price=20.0)

    # Owner creates a PO for one of its own products.
    resp = await client.post(
        "/api/v1/entities/purchase_orders",
        json={
            "order_number": "PO-STAFF",
            "status": "ordered",
            "items_json": json.dumps([{"product_id": pid, "quantity": 4, "cost": 5.0}]),
        },
        headers=owner_headers,
    )
    assert resp.status_code == 201, resp.text
    po_id = resp.json()["id"]

    # The cashier (a separate login under the merchant) receives it.
    _staff, staff_token = await _make_staff_login(client, owner["id"])
    r = await client.post(
        f"/api/v1/entities/purchase_orders/{po_id}/receive",
        json={},
        headers=auth_headers(staff_token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "received"

    # Stock landed against the owner's product.
    async with db_manager.async_session_maker() as db:
        from models.products import Products

        prod = (await db.execute(select(Products).where(Products.id == pid))).scalar_one()
        assert prod.quantity == 4

    # A different merchant cannot receive this PO (cross-tenant rejected).
    _other, other_token, _other_cid = await make_client_account(client)
    r2 = await client.post(
        f"/api/v1/entities/purchase_orders/{po_id}/receive",
        json={},
        headers=auth_headers(other_token),
    )
    assert r2.status_code == 404


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


@pytest.mark.asyncio
async def test_staff_can_use_owners_payment_gateway(client):
    """A cashier sub-user lists the owner's terminals and charges through the gateway.

    Regression for H17: ``payments_gateway.py`` scoped every op on the *caller's*
    ``current_user.id`` (``_client_for_user``, register/list/charge), so a cashier —
    who has no ``Clients`` row of their own — hit 403 on ``/charge`` and saw an empty
    ``/terminals``. The gateway must resolve the client via ``get_owner_id`` so a
    sub-user operates against the owning merchant's terminals.
    """
    owner, owner_token, _client_id = await make_client_account(client)
    owner_headers = auth_headers(owner_token)

    # Owner registers an in-store terminal.
    resp = await client.post(
        "/api/v1/payments/terminals",
        json={"provider": "geidea", "label": "Front Till"},
        headers=owner_headers,
    )
    assert resp.status_code == 201, resp.text
    terminal_id = resp.json()["id"]

    # The cashier (a separate login under the merchant) operates the gateway.
    _staff, staff_token = await _make_staff_login(client, owner["id"])
    staff_headers = auth_headers(staff_token)

    # The cashier lists the owner's terminals (not an empty private set).
    resp = await client.get("/api/v1/payments/terminals", headers=staff_headers)
    assert resp.status_code == 200, resp.text
    assert terminal_id in [t["id"] for t in resp.json()]

    # The cashier captures a card tender through the gateway.
    resp = await client.post(
        "/api/v1/payments/charge",
        json={"tender_type": "mada", "amount": 50.0, "simulate": "approve"},
        headers=staff_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["approved"] is True

    # The cashier pushes a charge to the owner's terminal.
    resp = await client.post(
        "/api/v1/payments/terminal/charge",
        json={"terminal_id": terminal_id, "amount": 25.0, "simulate": "approve"},
        headers=staff_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["approved"] is True


@pytest.mark.asyncio
async def test_cross_tenant_terminal_charge_rejected(client):
    """A different merchant cannot list or charge another merchant's terminal."""
    owner, owner_token, _client_id = await make_client_account(client)
    resp = await client.post(
        "/api/v1/payments/terminals",
        json={"provider": "geidea", "label": "Owner Till"},
        headers=auth_headers(owner_token),
    )
    assert resp.status_code == 201, resp.text
    terminal_id = resp.json()["id"]

    _other, other_token, _other_cid = await make_client_account(client)
    other_headers = auth_headers(other_token)

    # The other merchant does not see the owner's terminal.
    resp = await client.get("/api/v1/payments/terminals", headers=other_headers)
    assert resp.status_code == 200, resp.text
    assert terminal_id not in [t["id"] for t in resp.json()]

    # And cannot charge against it.
    resp = await client.post(
        "/api/v1/payments/terminal/charge",
        json={"terminal_id": terminal_id, "amount": 10.0, "simulate": "approve"},
        headers=other_headers,
    )
    assert resp.status_code == 404, resp.text
