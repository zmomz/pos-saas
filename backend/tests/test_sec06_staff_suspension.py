"""SEC-06 — staff inherit the owning merchant's suspension.

The active-check historically inspected only the *caller's own* ``Clients`` row.
A staff member has no client row under their own login, so a suspended merchant's
cashier kept full access. These tests pin the corrected behavior: the suspension
flag is read from the *owning* merchant (resolved exactly as tenancy does), while
master/agent accounts — which have no owner to suspend — stay unaffected.
"""
import uuid

from conftest import (
    auth_headers,
    make_agent_account,
    make_client_account,
    make_master_account,
    register_user,
    unique_email,
)
from core.database import db_manager
from models.staff_members import Staff_members


async def _attach_staff(owner_user_id: str, email: str) -> None:
    """Insert a ``Staff_members`` row mapping ``email`` -> ``owner_user_id``."""
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


async def test_staff_under_suspended_owner_is_blocked(client):
    owner, _, _ = await make_client_account(client, is_active=False)
    staff_email = unique_email()
    _, staff_token, _ = await register_user(client, email=staff_email)
    await _attach_staff(owner["id"], staff_email)

    resp = await client.get("/api/v1/auth/me", headers=auth_headers(staff_token))
    assert resp.status_code == 403, resp.text
    assert "suspended" in resp.json()["detail"].lower()


async def test_staff_under_active_owner_allowed(client):
    owner, _, _ = await make_client_account(client, is_active=True)
    staff_email = unique_email()
    _, staff_token, _ = await register_user(client, email=staff_email)
    await _attach_staff(owner["id"], staff_email)

    resp = await client.get("/api/v1/auth/me", headers=auth_headers(staff_token))
    assert resp.status_code == 200, resp.text


async def test_master_unaffected(client):
    _, token = await make_master_account(client)
    resp = await client.get("/api/v1/auth/me", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text


async def test_agent_unaffected(client):
    _, token, _ = await make_agent_account(client)
    resp = await client.get("/api/v1/auth/me", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
