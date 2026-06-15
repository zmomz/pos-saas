"""ISSUE-084 — configurable password-complexity policy.

Weak passwords must be rejected with a clear message at every set-password
entry point (signup, reset, change-password, staff-login provisioning), and the
policy itself must be tunable. Tests drive the public HTTP interface where one
exists, plus the shared ``validate_password_complexity`` primitive for the
configurability behavior.
"""
import pytest

from core.security import PasswordPolicyError, validate_password_complexity
from tests.conftest import (
    auth_headers,
    make_client_account,
    register_user,
    unique_email,
)


def test_validator_rejects_password_missing_a_character_class():
    """A password that satisfies length but lacks a required class is rejected
    with a message naming what is missing."""
    with pytest.raises(PasswordPolicyError) as exc:
        validate_password_complexity("alllowercase")  # no uppercase, no digit
    msg = str(exc.value)
    assert "uppercase" in msg
    assert "digit" in msg


def test_validator_accepts_a_compliant_password():
    """A mixed-case alphanumeric password meeting the default policy passes."""
    validate_password_complexity("Password123")  # must not raise


def test_policy_is_configurable(monkeypatch):
    """Tightening or relaxing the policy changes what the validator accepts."""
    from core.config import settings

    # Tighten: requiring a symbol now rejects an otherwise-compliant password.
    monkeypatch.setattr(settings, "password_require_symbol", True)
    with pytest.raises(PasswordPolicyError) as exc:
        validate_password_complexity("Password123")
    assert "symbol" in str(exc.value)
    validate_password_complexity("Password123!")  # satisfies the tighter rule

    # Relax: dropping the digit requirement and lowering the length accepts a
    # short, digit-free password that the default policy would reject.
    monkeypatch.setattr(settings, "password_require_symbol", False)
    monkeypatch.setattr(settings, "password_require_digit", False)
    monkeypatch.setattr(settings, "password_min_length", 4)
    validate_password_complexity("Abcd")


@pytest.mark.asyncio
async def test_register_rejects_weak_password(client):
    """Signup with a long-but-classless password is rejected with a clear message."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": unique_email(), "password": "alllowercase", "name": "X"},
    )
    assert resp.status_code == 422, resp.text
    assert "uppercase" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_register_accepts_strong_password(client):
    """A compliant signup still succeeds end-to-end."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": unique_email(), "password": "Password123", "name": "X"},
    )
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_reset_rejects_weak_new_password(client):
    """Completing a reset with a classless password is rejected, not applied."""
    email = unique_email()
    await register_user(client, email=email)
    forgot = await client.post("/api/v1/auth/password/forgot", json={"email": email})
    token = forgot.json()["reset_token"]  # surfaced in dev (ENVIRONMENT=dev)

    resp = await client.post(
        "/api/v1/auth/password/reset",
        json={"token": token, "new_password": "alllowercase"},
    )
    assert resp.status_code == 422, resp.text
    assert "uppercase" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_staff_provisioning_rejects_weak_supplied_password(client):
    """A merchant provisioning a staff login with a weak password is rejected."""
    _owner, owner_token, _client_id = await make_client_account(client)
    resp = await client.post(
        "/api/v1/entities/staff_members",
        json={
            "name": "Cashier",
            "email": unique_email(),
            "role": "cashier",
            "password": "alllowercase",
        },
        headers=auth_headers(owner_token),
    )
    assert resp.status_code == 422, resp.text
    assert "uppercase" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_change_password_rejects_weak_new_password(client):
    """An authenticated change-password to a classless value is rejected."""
    _user, token, _ = await register_user(client)
    resp = await client.post(
        "/api/v1/users/change-password",
        json={"current_password": "Password123", "new_password": "alllowercase"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 422, resp.text
    assert "uppercase" in resp.json()["detail"]
