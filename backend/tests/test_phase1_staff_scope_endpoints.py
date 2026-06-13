"""F-SEC-1: staff/cashier logins operate within the OWNING merchant's tenant
across the real HTTP endpoints (not just resolve_tenant_scope in isolation).

Before the fix, owner-scoped routers filtered by the caller's *own* user id, so a
cashier — who has no Clients row of their own — saw an empty catalog and could not
ring a sale (the POS path 403'd on ``get_client_for_user``). These tests drive the
endpoints with the *staff member's own token* and assert they see and act on the
merchant's data, and that records they create are owned by the merchant.
"""
import uuid

import pytest
from sqlalchemy import select

from core.database import db_manager
from models.staff_members import Staff_members
from models.transactions import Transactions

from conftest import (
    add_product,
    auth_headers,
    make_client_account,
    register_user,
    unique_email,
)


async def make_staff_login(client, owner_user_id: str):
    """Register a standalone cashier login and link a Staff_members row owned by
    the merchant (keyed on the cashier's email, as resolve_tenant_scope expects).

    Returns (staff_user, staff_token).
    """
    email = unique_email()
    staff_user, staff_token, _ = await register_user(client, email=email)
    async with db_manager.async_session_maker() as db:
        db.add(
            Staff_members(
                user_id=owner_user_id,
                name="Cashier",
                email=email,
                role="cashier",
                is_active=True,
            )
        )
        await db.commit()
    return staff_user, staff_token


@pytest.mark.asyncio
async def test_staff_sees_merchant_catalog_via_endpoints(client):
    owner, _owner_token, client_id = await make_client_account(client)
    name = f"Merchant-Widget-{uuid.uuid4().hex[:6]}"
    await add_product(client_id, owner["id"], name=name, quantity=7, price=12.0)

    _staff_user, staff_token = await make_staff_login(client, owner["id"])

    # The reporting/catalog surface (features.py -> get_user_role(owner_id)).
    resp = await client.get("/api/v1/products/list", headers=auth_headers(staff_token))
    assert resp.status_code == 200, resp.text
    names = [p["name"] for p in resp.json()["items"]]
    assert name in names, "cashier must see the merchant's catalog, not an empty tenant"

    # The generic CRUD triad surface (scope.owner_user_id).
    resp = await client.get("/api/v1/entities/products", headers=auth_headers(staff_token))
    assert resp.status_code == 200, resp.text
    assert name in [p["name"] for p in resp.json()["items"]]


@pytest.mark.asyncio
async def test_staff_can_ring_a_sale_owned_by_merchant(client):
    owner, _owner_token, client_id = await make_client_account(client)
    pid = await add_product(client_id, owner["id"], name="Cola", quantity=10, price=5.0)

    _staff_user, staff_token = await make_staff_login(client, owner["id"])

    resp = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Cola", "price": 5.0, "quantity": 2}],
            "payment_method": "cash",
        },
        headers=auth_headers(staff_token),
    )
    assert resp.status_code == 200, resp.text
    sale = resp.json()

    # The sale is persisted under the MERCHANT's tenancy (so the owner sees it),
    # even though a cashier rang it.
    async with db_manager.async_session_maker() as db:
        owner_id = (
            await db.execute(
                select(Transactions.user_id).where(Transactions.id == sale["id"])
            )
        ).scalar_one()
    assert owner_id == owner["id"]


@pytest.mark.asyncio
async def test_staff_cannot_see_a_foreign_merchants_catalog(client):
    """Owner-scoping must still isolate: a cashier sees ONLY their merchant (SEC-02)."""
    owner_a, _ta, client_a = await make_client_account(client)
    await add_product(client_a, owner_a["id"], name=f"A-only-{uuid.uuid4().hex[:6]}")

    owner_b, _tb, _client_b = await make_client_account(client)
    _staff_b_user, staff_b_token = await make_staff_login(client, owner_b["id"])

    resp = await client.get("/api/v1/products/list", headers=auth_headers(staff_b_token))
    assert resp.status_code == 200, resp.text
    names = [p["name"] for p in resp.json()["items"]]
    assert not any(n.startswith("A-only") for n in names), "cashier leaked into another tenant"
