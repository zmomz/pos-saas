"""ISSUE-081: optional MFA (TOTP) — enroll, challenge on login, recovery codes.

Tests drive the public HTTP interface. The test acts as the authenticator app:
it reads the enrollment secret and computes the current TOTP code through the
same shared generator the server uses (``core.totp``).
"""
from conftest import auth_headers, register_user, unique_email
from core.totp import totp_now


async def _enroll_and_activate(client, token):
    """Enroll + activate TOTP for a signed-in user; return (secret, recovery_codes)."""
    enroll = await client.post("/api/v1/auth/mfa/enroll", headers=auth_headers(token))
    secret = enroll.json()["secret"]
    activate = await client.post(
        "/api/v1/auth/mfa/activate",
        json={"code": totp_now(secret)},
        headers=auth_headers(token),
    )
    assert activate.status_code == 200, activate.text
    return secret, activate.json()["recovery_codes"]


async def test_enroll_returns_secret_and_provisioning_uri(client):
    """A signed-in user can begin TOTP enrollment and receive a secret + URI."""
    _, token, _ = await register_user(client)

    resp = await client.post("/api/v1/auth/mfa/enroll", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["secret"]  # base32 shared secret for the authenticator app
    assert body["otpauth_uri"].startswith("otpauth://totp/")
    # Enrollment is not active until a code is verified.
    assert body.get("enabled") is False


async def test_activate_with_valid_code_enables_mfa_and_returns_recovery_codes(client):
    """Verifying a real TOTP code activates MFA and hands back recovery codes."""
    _, token, _ = await register_user(client)

    enroll = await client.post("/api/v1/auth/mfa/enroll", headers=auth_headers(token))
    secret = enroll.json()["secret"]

    # A wrong code does not activate.
    bad = await client.post(
        "/api/v1/auth/mfa/activate", json={"code": "000000"}, headers=auth_headers(token)
    )
    assert bad.status_code == 400

    activate = await client.post(
        "/api/v1/auth/mfa/activate", json={"code": totp_now(secret)}, headers=auth_headers(token)
    )
    assert activate.status_code == 200, activate.text
    codes = activate.json()["recovery_codes"]
    assert isinstance(codes, list) and len(codes) >= 8

    status = await client.get("/api/v1/auth/mfa/status", headers=auth_headers(token))
    assert status.status_code == 200
    assert status.json()["enabled"] is True


async def test_login_with_mfa_enabled_returns_challenge_not_token(client):
    """A correct password alone no longer logs an MFA user in — it challenges."""
    email = unique_email()
    _, token, _ = await register_user(client, email=email, password="Password123")
    await _enroll_and_activate(client, token)

    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "Password123"}
    )
    assert login.status_code == 200, login.text
    body = login.json()
    assert body.get("mfa_required") is True
    assert body.get("mfa_token")  # short-lived second-factor ticket
    assert body.get("token") is None  # no access token until the 2nd factor


async def test_login_without_mfa_still_returns_token(client):
    """Regression: users who never enabled MFA log in directly, unchanged."""
    email = unique_email()
    await register_user(client, email=email, password="Password123")
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "Password123"}
    )
    assert login.status_code == 200, login.text
    body = login.json()
    assert body.get("token")
    assert body.get("mfa_required") in (None, False)


async def test_second_factor_with_totp_returns_working_token(client):
    """Exchanging the challenge ticket + a current TOTP code mints a real token."""
    email = unique_email()
    _, token, _ = await register_user(client, email=email, password="Password123")
    secret, _ = await _enroll_and_activate(client, token)

    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "Password123"}
    )
    mfa_token = login.json()["mfa_token"]

    # A wrong code is rejected.
    bad = await client.post(
        "/api/v1/auth/login/mfa", json={"mfa_token": mfa_token, "code": "000000"}
    )
    assert bad.status_code == 401

    ok = await client.post(
        "/api/v1/auth/login/mfa", json={"mfa_token": mfa_token, "code": totp_now(secret)}
    )
    assert ok.status_code == 200, ok.text
    access = ok.json()["token"]
    assert ok.json().get("refresh_token")

    # The minted token actually authenticates.
    me = await client.get("/api/v1/auth/me", headers=auth_headers(access))
    assert me.status_code == 200
    assert me.json()["email"] == email

    # The MFA ticket itself cannot be used as an access token.
    misused = await client.get("/api/v1/auth/me", headers=auth_headers(mfa_token))
    assert misused.status_code == 401


async def test_recovery_code_works_once_then_is_rejected(client):
    """A recovery code completes a login exactly once; a reuse is rejected."""
    email = unique_email()
    _, token, _ = await register_user(client, email=email, password="Password123")
    _, recovery_codes = await _enroll_and_activate(client, token)
    code = recovery_codes[0]

    async def challenge():
        login = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": "Password123"}
        )
        return login.json()["mfa_token"]

    # First use: the recovery code logs in.
    first = await client.post(
        "/api/v1/auth/login/mfa", json={"mfa_token": await challenge(), "code": code}
    )
    assert first.status_code == 200, first.text
    assert first.json()["token"]

    # Second use of the SAME code: rejected (single-use).
    second = await client.post(
        "/api/v1/auth/login/mfa", json={"mfa_token": await challenge(), "code": code}
    )
    assert second.status_code == 401

    # One code consumed -> remaining count dropped by one.
    st = await client.get("/api/v1/auth/mfa/status", headers=auth_headers(token))
    assert st.json()["recovery_codes_remaining"] == len(recovery_codes) - 1
