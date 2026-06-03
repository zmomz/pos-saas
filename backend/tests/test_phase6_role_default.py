"""F-031 — SEC-02 least-privilege: features.py::get_user_role must NOT default
an unknown account to ``master``.

Regression guard for a privilege-escalation divergence: ``features.py``'s role
helper used to return ``role="master"`` for any account with no agent/client row
(the opposite of ``tenant.py``), and it is the only gate on the ``packages`` CRUD
(``/api/v1/packages/*``). A self-registered user with no tenancy row could thus be
treated as the platform master for package management.

These tests pin the corrected behaviour: unknown account -> ``client``; ``master``
only for an explicitly-seeded admin (``User.role == 'admin'``).
"""
import pytest

from core.database import db_manager
from routers.features import get_user_role

from conftest import (
    auth_headers,
    make_master_account,
    register_user,
)


@pytest.mark.asyncio
async def test_features_role_helper_defaults_unknown_account_to_client(client):
    """A registered user with no agent/client row resolves as client, not master."""
    user, _token, _refresh = await register_user(client)
    async with db_manager.async_session_maker() as db:
        role_info = await get_user_role(db, str(user["id"]))
    assert role_info["role"] == "client"
    assert role_info["entity_id"] is None


@pytest.mark.asyncio
async def test_features_role_helper_grants_master_only_to_admin(client):
    """An explicitly-seeded admin (User.role='admin') still resolves as master."""
    user, _token = await make_master_account(client)
    async with db_manager.async_session_maker() as db:
        role_info = await get_user_role(db, str(user["id"]))
    assert role_info["role"] == "master"


@pytest.mark.asyncio
async def test_self_registered_user_cannot_manage_packages(client):
    """The packages CRUD is gated by get_user_role -> a plain user gets 403."""
    _user, token, _refresh = await register_user(client)
    resp = await client.get("/api/v1/packages/list", headers=auth_headers(token))
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_master_can_manage_packages(client):
    """An admin master still reaches the packages CRUD (200, not 403)."""
    _user, token = await make_master_account(client)
    resp = await client.get("/api/v1/packages/list", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
