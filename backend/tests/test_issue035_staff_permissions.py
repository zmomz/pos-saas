"""ISSUE-035 — owner-scoped staff-permission editor.

The RBAC engine (ISSUE-034) gates managed POS keys by a staff member's *role*,
but a merchant had no way to override a role's default for an individual staff
member. These endpoints back the management UI:

* ``GET  /production/staff-permissions/{staff_member_id}`` — the effective map
  (role default + explicit override) for the owner's staff member;
* ``POST /production/staff-permissions/{staff_member_id}`` — set a grant/deny
  override (or reset to the role default) keyed on the staff member's *login*
  user id, so it takes effect in ``has_permission`` over the role default.

Both are owner-scoped: a merchant can only touch their own staff (cross-tenant
edits are rejected).
"""
import pytest
from sqlalchemy import select

from conftest import auth_headers, make_client_account, unique_email
from core.database import db_manager
from dependencies.permissions import has_permission
from models.auth import User

STAFF_URL = "/api/v1/entities/staff_members"
PERMS_URL = "/api/v1/production/staff-permissions"
SENSITIVE_KEYS = ("pos.refund", "pos.void", "pos.discount", "pos.price_override")


async def _provision_staff(client, owner_token, role):
    """Create a staff member with a login; return (staff_member_id, login_user_id)."""
    email = unique_email()
    resp = await client.post(
        STAFF_URL,
        json={"name": role.title(), "email": email, "role": role},
        headers=auth_headers(owner_token),
    )
    assert resp.status_code == 201, resp.text
    staff_id = resp.json()["id"]
    async with db_manager.async_session_maker() as db:
        uid = (
            await db.execute(select(User.id).where(User.email == email))
        ).scalar_one()
    return staff_id, str(uid)


@pytest.mark.asyncio
async def test_owner_deny_override_takes_effect(client):
    """AC1/AC2: an owner can deny a managed key a manager's role would grant,
    and the override takes effect in ``has_permission``."""
    _owner, token, _client_id = await make_client_account(client)
    staff_id, login_uid = await _provision_staff(client, token, "manager")

    # Sanity: the manager role grants pos.void by default.
    async with db_manager.async_session_maker() as db:
        assert await has_permission(db, login_uid, "pos.void") is True

    resp = await client.post(
        f"{PERMS_URL}/{staff_id}",
        headers=auth_headers(token),
        json={"permission_key": "pos.void", "is_granted": False},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["effective"] is False

    async with db_manager.async_session_maker() as db:
        assert await has_permission(db, login_uid, "pos.void") is False
        # Other managed keys are untouched by the single override.
        assert await has_permission(db, login_uid, "pos.refund") is True


@pytest.mark.asyncio
async def test_owner_grant_override_restores_cashier_key(client):
    """AC1/AC2: an owner can grant a cashier a key the role would deny."""
    _owner, token, _client_id = await make_client_account(client)
    staff_id, login_uid = await _provision_staff(client, token, "cashier")

    async with db_manager.async_session_maker() as db:
        assert await has_permission(db, login_uid, "pos.refund") is False

    resp = await client.post(
        f"{PERMS_URL}/{staff_id}",
        headers=auth_headers(token),
        json={"permission_key": "pos.refund", "is_granted": True},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["effective"] is True

    async with db_manager.async_session_maker() as db:
        assert await has_permission(db, login_uid, "pos.refund") is True
        # A key with no override stays denied by the cashier default.
        assert await has_permission(db, login_uid, "pos.void") is False


@pytest.mark.asyncio
async def test_get_returns_effective_map(client):
    """AC1: GET surfaces role default, override, and effective per managed key."""
    _owner, token, _client_id = await make_client_account(client)
    staff_id, _login_uid = await _provision_staff(client, token, "cashier")

    # Override one key so the map reflects both default and override columns.
    await client.post(
        f"{PERMS_URL}/{staff_id}",
        headers=auth_headers(token),
        json={"permission_key": "pos.discount", "is_granted": True},
    )

    resp = await client.get(f"{PERMS_URL}/{staff_id}", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["role"] == "cashier"
    assert body["has_login"] is True
    by_key = {p["permission_key"]: p for p in body["permissions"]}
    assert set(by_key) == set(SENSITIVE_KEYS)
    # The overridden key: cashier default deny, override grant, effective grant.
    assert by_key["pos.discount"] == {
        "permission_key": "pos.discount",
        "role_default": False,
        "override": True,
        "effective": True,
    }
    # An un-overridden key keeps the cashier default (deny), no override row.
    assert by_key["pos.refund"]["override"] is None
    assert by_key["pos.refund"]["effective"] is False


@pytest.mark.asyncio
async def test_reset_reverts_to_role_default(client):
    """AC1: posting is_granted=null drops the override; the key reverts to default."""
    _owner, token, _client_id = await make_client_account(client)
    staff_id, login_uid = await _provision_staff(client, token, "manager")

    # Deny a key the manager would otherwise have, then reset it.
    await client.post(
        f"{PERMS_URL}/{staff_id}",
        headers=auth_headers(token),
        json={"permission_key": "pos.void", "is_granted": False},
    )
    async with db_manager.async_session_maker() as db:
        assert await has_permission(db, login_uid, "pos.void") is False

    resp = await client.post(
        f"{PERMS_URL}/{staff_id}",
        headers=auth_headers(token),
        json={"permission_key": "pos.void", "is_granted": None},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["override"] is None
    assert resp.json()["effective"] is True  # back to the manager default

    async with db_manager.async_session_maker() as db:
        assert await has_permission(db, login_uid, "pos.void") is True


@pytest.mark.asyncio
async def test_cross_tenant_edit_rejected(client):
    """AC3: a merchant cannot edit another merchant's staff member."""
    _owner_a, token_a, _client_a = await make_client_account(client)
    staff_a, login_a = await _provision_staff(client, token_a, "manager")

    _owner_b, token_b, _client_b = await make_client_account(client)

    # B tries to deny A's manager — rejected, A's permissions untouched.
    resp = await client.post(
        f"{PERMS_URL}/{staff_a}",
        headers=auth_headers(token_b),
        json={"permission_key": "pos.void", "is_granted": False},
    )
    assert resp.status_code == 404, resp.text

    # B also cannot read A's staff permission map.
    get_resp = await client.get(f"{PERMS_URL}/{staff_a}", headers=auth_headers(token_b))
    assert get_resp.status_code == 404, get_resp.text

    async with db_manager.async_session_maker() as db:
        assert await has_permission(db, login_a, "pos.void") is True


@pytest.mark.asyncio
async def test_unknown_permission_key_rejected(client):
    """An unmanaged/unknown key is a 400 rather than a silently-written row."""
    _owner, token, _client_id = await make_client_account(client)
    staff_id, _login_uid = await _provision_staff(client, token, "cashier")

    resp = await client.post(
        f"{PERMS_URL}/{staff_id}",
        headers=auth_headers(token),
        json={"permission_key": "pos.nonsense", "is_granted": True},
    )
    assert resp.status_code == 400, resp.text
