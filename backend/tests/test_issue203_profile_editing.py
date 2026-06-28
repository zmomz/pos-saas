"""#203 / parity #4 — profile name / email / phone editing.

``PUT /users/profile`` previously accepted only ``name``. It now also persists
``email`` (normalised + uniqueness-checked) and ``phone`` so the ``UserProfile``
page can let a user edit their own account. These tests drive the corrected
behaviour through the public HTTP API.
"""
from conftest import auth_headers, register_user, unique_email


async def test_get_profile_includes_phone_field(client):
    _, token, _ = await register_user(client)
    resp = await client.get("/api/v1/users/profile", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # phone is part of the contract now (null until set).
    assert "phone" in body
    assert body["phone"] is None


async def test_update_name_email_phone_persists(client):
    email = unique_email()
    _, token, _ = await register_user(client, email=email)

    new_email = unique_email()
    resp = await client.put(
        "/api/v1/users/profile",
        headers=auth_headers(token),
        json={"name": "Sara Ahmed", "email": new_email, "phone": "+966500000000"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "Sara Ahmed"
    assert body["email"] == new_email.lower()
    assert body["phone"] == "+966500000000"

    # Persisted: a fresh GET reflects the change.
    again = await client.get("/api/v1/users/profile", headers=auth_headers(token))
    assert again.json()["email"] == new_email.lower()
    assert again.json()["phone"] == "+966500000000"


async def test_email_is_normalised(client):
    _, token, _ = await register_user(client)
    mixed = "Mixed.Case+" + unique_email()
    # force uppercase local part
    target = mixed.upper()
    resp = await client.put(
        "/api/v1/users/profile",
        headers=auth_headers(token),
        json={"email": target},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["email"] == target.strip().lower()


async def test_blank_phone_clears_it(client):
    _, token, _ = await register_user(client)
    await client.put(
        "/api/v1/users/profile",
        headers=auth_headers(token),
        json={"phone": "123456"},
    )
    cleared = await client.put(
        "/api/v1/users/profile",
        headers=auth_headers(token),
        json={"phone": ""},
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["phone"] is None


async def test_duplicate_email_is_rejected(client):
    taken = unique_email()
    await register_user(client, email=taken)

    _, token, _ = await register_user(client)
    resp = await client.put(
        "/api/v1/users/profile",
        headers=auth_headers(token),
        json={"email": taken},
    )
    assert resp.status_code == 409, resp.text
    assert "use" in resp.json()["detail"].lower()


async def test_invalid_email_is_rejected(client):
    _, token, _ = await register_user(client)
    resp = await client.put(
        "/api/v1/users/profile",
        headers=auth_headers(token),
        json={"email": "not-an-email"},
    )
    assert resp.status_code == 422, resp.text


async def test_keeping_own_email_is_not_a_conflict(client):
    email = unique_email()
    _, token, _ = await register_user(client, email=email)
    # Re-submitting the same email (just changing the name) must not 409.
    resp = await client.put(
        "/api/v1/users/profile",
        headers=auth_headers(token),
        json={"name": "Renamed", "email": email},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "Renamed"
