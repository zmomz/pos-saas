"""SEC-10 — self-serve registration must be fail-secure (disabled by default).

In a wholesale-quota model accounts are provisioned (by master/agents), not
self-minted, so open registration should be OFF unless a deployment explicitly
opts in. These tests pin (1) the shipped default, (2) the endpoint guard in both
states, and (3) that provisioning paths are untouched by the flag.
"""
import uuid

from conftest import auth_headers, register_user, unique_email
from core.config import Settings, settings


def test_registration_disabled_by_default():
    """The shipped default for self-registration is OFF (fail-secure)."""
    assert Settings.model_fields["allow_registration"].default is False


async def test_register_403_when_disabled(client, monkeypatch):
    """With registration disabled, POST /register is rejected and mints nothing."""
    monkeypatch.setattr(settings, "allow_registration", False)
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": unique_email(), "password": "Password123", "name": "Nope"},
    )
    assert resp.status_code == 403, resp.text


async def test_register_201_when_enabled(client, monkeypatch):
    """An explicit opt-in (allow_registration=True) still lets users self-register."""
    monkeypatch.setattr(settings, "allow_registration", True)
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": unique_email(), "password": "Password123", "name": "Yes"},
    )
    assert resp.status_code == 201, resp.text


async def test_provisioning_unaffected_when_registration_disabled(client, monkeypatch):
    """Master provisioning (create_agent) does not go through the /register guard,
    so disabling self-registration must not break account provisioning."""
    # Master is provisioned before the flag flips (registration on by env default).
    from sqlalchemy import update

    from core.database import db_manager
    from models.auth import User

    user, token, _ = await register_user(client)
    async with db_manager.async_session_maker() as db:
        await db.execute(update(User).where(User.id == user["id"]).values(role="admin"))
        await db.commit()

    # Now lock down self-registration and confirm provisioning still works.
    monkeypatch.setattr(settings, "allow_registration", False)
    resp = await client.post(
        "/api/v1/tenant/master/agents",
        headers=auth_headers(token),
        json={
            "company_name": "Provisioned Co",
            "email": f"agent_{uuid.uuid4().hex[:10]}@example.com",
            "slots": 1,
        },
    )
    assert resp.status_code in (200, 201), resp.text
