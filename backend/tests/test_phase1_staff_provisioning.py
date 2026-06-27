"""ISSUE-033: staff login provisioning.

StaffManagement create wrote a ``Staff_members`` row with no auth ``User`` and no
password/invite, so a "cashier" could never log in — tenancy resolution matches
``Staff_members.email`` to an *existing* ``User.email`` that nothing created.

These tests drive the real create endpoint as the merchant and assert the newly
created staff member can authenticate and, once logged in, resolves to the owning
merchant's tenant (shared catalog), never a private empty one.
"""
import pytest

from conftest import (
    add_product,
    auth_headers,
    make_client_account,
    unique_email,
)

STAFF_URL = "/api/v1/entities/staff_members"


@pytest.mark.asyncio
async def test_create_staff_provisions_a_login_scoped_to_owner(client):
    """AC1+AC2+AC3+AC4: creating a staff member with an email provisions an auth
    user; that staff member can log in with the returned temp password and is
    scoped to the owning merchant (sees the merchant's catalog)."""
    owner, owner_token, client_id = await make_client_account(client)
    await add_product(client_id, owner["id"], name="Merchant-Widget", quantity=4, price=9.0)

    staff_email = unique_email()
    create = await client.post(
        STAFF_URL,
        json={"name": "Cashier", "email": staff_email, "role": "cashier"},
        headers=auth_headers(owner_token),
    )
    assert create.status_code == 201, create.text
    body = create.json()
    # A temp password is handed back once so the merchant can relay it.
    temp_password = body.get("temp_password")
    assert temp_password, f"expected a temp_password on creation, got {body!r}"

    # The cashier can authenticate with that temp password.
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": staff_email, "password": temp_password},
    )
    assert login.status_code == 200, login.text
    staff_token = login.json()["token"]

    # SEC-07: the provisioned cashier must rotate the temp password before they
    # may operate; the change clears the force-reset flag.
    changed = await client.post(
        "/api/v1/users/change-password",
        json={"current_password": temp_password, "new_password": "BrandNew123"},
        headers=auth_headers(staff_token),
    )
    assert changed.status_code == 200, changed.text

    # And, logged in, the cashier operates within the merchant's tenant: it sees
    # the merchant's product rather than an empty private catalog.
    listing = await client.get("/api/v1/products/list", headers=auth_headers(staff_token))
    assert listing.status_code == 200, listing.text
    names = [p.get("name") for p in listing.json().get("items", [])]
    assert "Merchant-Widget" in names


@pytest.mark.asyncio
async def test_create_staff_with_supplied_password_does_not_leak_temp(client):
    """When the merchant sets an initial password, the staff member logs in with it
    and no temp password is echoed back (only generated ones are surfaced once)."""
    _owner, owner_token, _client_id = await make_client_account(client)
    staff_email = unique_email()

    create = await client.post(
        STAFF_URL,
        json={"name": "Cashier", "email": staff_email, "role": "cashier", "password": "Chosen123"},
        headers=auth_headers(owner_token),
    )
    assert create.status_code == 201, create.text
    assert create.json().get("temp_password") is None

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": staff_email, "password": "Chosen123"},
    )
    assert login.status_code == 200, login.text


@pytest.mark.asyncio
async def test_create_staff_without_email_is_directory_only(client):
    """A staff member created without an email is a directory entry: no login is
    provisioned and no temp password is returned (nothing to sign in with)."""
    _owner, owner_token, _client_id = await make_client_account(client)

    create = await client.post(
        STAFF_URL,
        json={"name": "Floor Helper", "role": "cashier"},
        headers=auth_headers(owner_token),
    )
    assert create.status_code == 201, create.text
    assert create.json().get("temp_password") is None
