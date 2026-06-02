"""Auth lifecycle tests: refresh tokens and change-password."""
from conftest import auth_headers, register_user, unique_email


async def test_register_and_login_issue_refresh_token(client):
    email = unique_email()
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123", "name": "A"},
    )
    assert reg.status_code == 201, reg.text
    assert reg.json().get("refresh_token")

    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "Password123"})
    assert login.status_code == 200, login.text
    assert login.json().get("refresh_token")


async def test_refresh_token_flow(client):
    _, token, refresh = await register_user(client)

    # A valid refresh token mints a new access token.
    ok = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert ok.status_code == 200, ok.text
    new_token = ok.json()["token"]
    me = await client.get("/api/v1/auth/me", headers=auth_headers(new_token))
    assert me.status_code == 200

    # An access token cannot be used at the refresh endpoint.
    bad = await client.post("/api/v1/auth/refresh", json={"refresh_token": token})
    assert bad.status_code == 401

    # A refresh token cannot be used as an access token.
    misused = await client.get("/api/v1/auth/me", headers=auth_headers(refresh))
    assert misused.status_code == 401


async def test_change_password(client):
    email = unique_email()
    _, token, _ = await register_user(client, email=email, password="Password123")
    headers = auth_headers(token)

    # Wrong current password.
    wrong = await client.post(
        "/api/v1/users/change-password",
        json={"current_password": "WrongPass1", "new_password": "NewPassw0rd"},
        headers=headers,
    )
    assert wrong.status_code == 400

    # Same password rejected.
    same = await client.post(
        "/api/v1/users/change-password",
        json={"current_password": "Password123", "new_password": "Password123"},
        headers=headers,
    )
    assert same.status_code == 400

    # Correct change.
    ok = await client.post(
        "/api/v1/users/change-password",
        json={"current_password": "Password123", "new_password": "NewPassw0rd"},
        headers=headers,
    )
    assert ok.status_code == 200, ok.text

    # Old password no longer works; new one does.
    old = await client.post("/api/v1/auth/login", json={"email": email, "password": "Password123"})
    assert old.status_code == 401
    new = await client.post("/api/v1/auth/login", json={"email": email, "password": "NewPassw0rd"})
    assert new.status_code == 200
