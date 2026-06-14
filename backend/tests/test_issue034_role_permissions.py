"""ISSUE-034: a role→permission default map drives ``has_permission``.

A real merchant's staff are created with a ``Staff_members.role`` ("cashier" /
"manager" / "admin") but no per-key grant/deny rows, so ``require_permission``
only ever fired for hand-seeded data — a cashier could refund/void/discount
freely. ``has_permission`` now resolves a logged-in staff member back to their
role and consults a default map: a managed key (pos.refund/void/discount/
price_override) is allowed only where the role grants it, while an explicit
``Permissions`` row (deny or grant) still overrides the default.

These tests drive ``has_permission`` (the gate behind ``require_permission`` and
the pos.py inline checks) directly, provisioning staff through the real create
endpoint so the email→role resolution is exercised end-to-end.
"""
import pytest
from sqlalchemy import select

from conftest import auth_headers, make_client_account, unique_email
from core.database import db_manager
from dependencies.permissions import has_permission
from models.auth import User

STAFF_URL = "/api/v1/entities/staff_members"
SENSITIVE_KEYS = ("pos.refund", "pos.void", "pos.discount", "pos.price_override")


async def _provision_staff(client, owner_token, role):
    """Create a staff member with a login and return its auth-user id."""
    email = unique_email()
    resp = await client.post(
        STAFF_URL,
        json={"name": role.title(), "email": email, "role": role},
        headers=auth_headers(owner_token),
    )
    assert resp.status_code == 201, resp.text
    async with db_manager.async_session_maker() as db:
        uid = (
            await db.execute(select(User.id).where(User.email == email))
        ).scalar_one()
    return str(uid)


@pytest.mark.asyncio
async def test_cashier_denied_sensitive_permissions_by_default(client):
    """AC2: a cashier role is denied the managed POS permissions by default."""
    _owner, owner_token, _client_id = await make_client_account(client)
    cashier_id = await _provision_staff(client, owner_token, "cashier")

    async with db_manager.async_session_maker() as db:
        for key in SENSITIVE_KEYS:
            assert await has_permission(db, cashier_id, key) is False, key


@pytest.mark.asyncio
async def test_manager_allowed_sensitive_permissions_by_default(client):
    """AC2: a manager role is allowed the managed POS permissions by default."""
    _owner, owner_token, _client_id = await make_client_account(client)
    manager_id = await _provision_staff(client, owner_token, "manager")

    async with db_manager.async_session_maker() as db:
        for key in SENSITIVE_KEYS:
            assert await has_permission(db, manager_id, key) is True, key


@pytest.mark.asyncio
async def test_merchant_owner_keeps_grant_by_default(client):
    """AC1: a non-staff account owner is not role-gated — keeps grant-by-default."""
    owner, _owner_token, _client_id = await make_client_account(client)

    async with db_manager.async_session_maker() as db:
        for key in SENSITIVE_KEYS:
            assert await has_permission(db, str(owner["id"]), key) is True, key


@pytest.mark.asyncio
async def test_explicit_deny_overrides_manager_role_default(client):
    """AC1: an explicit deny row revokes a capability the role would grant."""
    from models.permissions import Permissions

    _owner, owner_token, _client_id = await make_client_account(client)
    manager_id = await _provision_staff(client, owner_token, "manager")

    async with db_manager.async_session_maker() as db:
        db.add(
            Permissions(
                user_id=manager_id, permission_key="pos.void", is_granted=False
            )
        )
        await db.commit()

    async with db_manager.async_session_maker() as db:
        assert await has_permission(db, manager_id, "pos.void") is False
        # Other managed keys are untouched by the single override.
        assert await has_permission(db, manager_id, "pos.refund") is True


@pytest.mark.asyncio
async def test_explicit_grant_overrides_cashier_role_default(client):
    """AC1: an explicit grant row restores a capability the role would deny."""
    from models.permissions import Permissions

    _owner, owner_token, _client_id = await make_client_account(client)
    cashier_id = await _provision_staff(client, owner_token, "cashier")

    async with db_manager.async_session_maker() as db:
        db.add(
            Permissions(
                user_id=cashier_id, permission_key="pos.refund", is_granted=True
            )
        )
        await db.commit()

    async with db_manager.async_session_maker() as db:
        assert await has_permission(db, cashier_id, "pos.refund") is True
        # A capability with no override is still denied by the cashier default.
        assert await has_permission(db, cashier_id, "pos.void") is False
