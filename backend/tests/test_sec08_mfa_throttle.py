"""SEC-08: throttle second-factor (MFA) code attempts.

``/auth/login/mfa`` previously let an attacker burn unlimited TOTP / recovery
guesses against a held challenge ticket (the ticket lives ~5 min and the TOTP
window is only 6 digits, so unbounded guessing is a real brute-force vector).

These tests drive the public HTTP interface. The test acts as the authenticator
app, reading the enrollment secret and computing real codes via ``core.totp``.
The throttle reuses ``services.login_throttle`` keyed on the MFA subject, so the
default policy is ``login_max_attempts`` (5) failures before lockout.
"""
from conftest import auth_headers, register_user, unique_email
from core.config import settings
from core.totp import totp_now


async def _enroll_and_activate(client, token):
    enroll = await client.post("/api/v1/auth/mfa/enroll", headers=auth_headers(token))
    secret = enroll.json()["secret"]
    activate = await client.post(
        "/api/v1/auth/mfa/activate",
        json={"code": totp_now(secret)},
        headers=auth_headers(token),
    )
    assert activate.status_code == 200, activate.text
    return secret, activate.json()["recovery_codes"]


async def _challenge(client, email, password="Password123"):
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    return login.json()["mfa_token"]


async def test_mfa_locks_out_after_max_failed_code_attempts(client):
    """After ``login_max_attempts`` bad codes the ticket is invalidated (429)."""
    email = unique_email()
    _, token, _ = await register_user(client, email=email, password="Password123")
    secret, _ = await _enroll_and_activate(client, token)
    mfa_token = await _challenge(client, email)

    # Burn the budget with wrong codes; each is rejected with 401.
    for _ in range(settings.login_max_attempts):
        bad = await client.post(
            "/api/v1/auth/login/mfa", json={"mfa_token": mfa_token, "code": "000000"}
        )
        assert bad.status_code == 401, bad.text

    # The ticket is now invalidated: even a *valid* TOTP code is refused (429).
    blocked = await client.post(
        "/api/v1/auth/login/mfa", json={"mfa_token": mfa_token, "code": totp_now(secret)}
    )
    assert blocked.status_code == 429, blocked.text
    assert blocked.headers.get("Retry-After")


async def test_valid_code_within_budget_still_succeeds(client):
    """A wrong guess before a correct one (under the budget) still logs in."""
    email = unique_email()
    _, token, _ = await register_user(client, email=email, password="Password123")
    secret, _ = await _enroll_and_activate(client, token)
    mfa_token = await _challenge(client, email)

    # One wrong attempt, well under the lockout threshold.
    bad = await client.post(
        "/api/v1/auth/login/mfa", json={"mfa_token": mfa_token, "code": "000000"}
    )
    assert bad.status_code == 401, bad.text

    ok = await client.post(
        "/api/v1/auth/login/mfa", json={"mfa_token": mfa_token, "code": totp_now(secret)}
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["token"]


async def test_recovery_and_totp_attempts_share_the_counter(client):
    """Mixed wrong recovery-code and wrong TOTP guesses count toward one lockout."""
    email = unique_email()
    _, token, _ = await register_user(client, email=email, password="Password123")
    secret, recovery_codes = await _enroll_and_activate(client, token)
    mfa_token = await _challenge(client, email)

    # Interleave invalid recovery codes and invalid TOTP codes. Together they
    # must reach the same shared threshold rather than each getting a fresh budget.
    for i in range(settings.login_max_attempts):
        code = "ZZZZ-ZZZZ" if i % 2 == 0 else "000000"
        bad = await client.post(
            "/api/v1/auth/login/mfa", json={"mfa_token": mfa_token, "code": code}
        )
        assert bad.status_code == 401, bad.text

    # Budget exhausted across both code types -> locked out.
    blocked = await client.post(
        "/api/v1/auth/login/mfa", json={"mfa_token": mfa_token, "code": totp_now(secret)}
    )
    assert blocked.status_code == 429, blocked.text
