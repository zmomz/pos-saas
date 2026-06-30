"""#203 (M1·Auth, parity #4): users can edit their own name, email and phone.

The account profile endpoint (``/api/v1/users/profile``) previously only let a
user change their display ``name`` — ``email`` was read-only and there was no
``phone`` at all. These tests pin the full editable triple through the public
HTTP interface, plus the email-uniqueness guard that keeps the login identifier
unambiguous.
"""
import pytest

from tests.conftest import auth_headers, register_user, unique_email

pytestmark = pytest.mark.asyncio


async def test_profile_returns_name_email_phone(client):
    """GET /profile surfaces the account identity fields (phone null until set)."""
    user, token, _ = await register_user(client)

    resp = await client.get("/api/v1/users/profile", headers=auth_headers(token))

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["email"] == user["email"]
    assert body["name"] == "Test User"
    assert body["phone"] is None


async def test_name_email_phone_edits_persist(client):
    """PUT /profile persists all three fields; a fresh GET reads them back."""
    _user, token, _ = await register_user(client)
    new_email = unique_email()

    put = await client.put(
        "/api/v1/users/profile",
        headers=auth_headers(token),
        json={"name": "Jane Doe", "email": new_email, "phone": "+966500000000"},
    )
    assert put.status_code == 200, put.text
    assert put.json()["name"] == "Jane Doe"
    assert put.json()["email"] == new_email
    assert put.json()["phone"] == "+966500000000"

    reload = await client.get("/api/v1/users/profile", headers=auth_headers(token))
    assert reload.status_code == 200, reload.text
    body = reload.json()
    assert body["name"] == "Jane Doe"
    assert body["email"] == new_email
    assert body["phone"] == "+966500000000"


async def test_partial_update_leaves_other_fields_untouched(client):
    """Omitting a field leaves the stored value untouched (PATCH-like semantics)."""
    user, token, _ = await register_user(client)

    put = await client.put(
        "/api/v1/users/profile",
        headers=auth_headers(token),
        json={"phone": "+966511111111"},
    )
    assert put.status_code == 200, put.text
    body = put.json()
    assert body["phone"] == "+966511111111"
    # name/email unchanged
    assert body["name"] == "Test User"
    assert body["email"] == user["email"]


async def test_email_must_be_unique(client):
    """Editing email to one already used by another account is rejected (409)."""
    other, _, _ = await register_user(client)
    _me, my_token, _ = await register_user(client)

    resp = await client.put(
        "/api/v1/users/profile",
        headers=auth_headers(my_token),
        json={"email": other["email"]},
    )
    assert resp.status_code == 409, resp.text


async def test_keeping_own_email_is_allowed(client):
    """Re-submitting the user's own email (e.g. on a name edit) is not a conflict."""
    me, token, _ = await register_user(client)

    resp = await client.put(
        "/api/v1/users/profile",
        headers=auth_headers(token),
        json={"name": "Renamed", "email": me["email"]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["email"] == me["email"]
