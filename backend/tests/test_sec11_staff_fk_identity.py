"""SEC-11: bind staff identity to its tenant via an explicit FK, not an email match.

Tenancy and permission resolution used to map a logged-in account to its owning
merchant by matching the *mutable* ``User.email`` against ``Staff_members.email``.
That string join is a tenant boundary an attacker can hijack: pre-register the
email a merchant will later add as staff and the attacker's own account
email-matches the staff row, inheriting the merchant's tenant.

The fix introduces ``Staff_members.login_user_id`` — the staff member's *own*
login account id (distinct from ``user_id``, which is the owning merchant) — and
resolves on that FK. These tests drive the real resolvers and the staff-create
endpoint and assert:

* resolution follows the FK, so changing the login's email does not move tenants;
* provisioning links a *freshly created* login by FK (ownership by construction);
* a pre-existing account is NOT auto-linked (the hijack is closed);
* the permission resolver likewise keys on the FK, not the email.
"""
import uuid

import pytest

from core.database import db_manager
from dependencies.tenancy import resolve_tenant_scope
from dependencies.permissions import _staff_role_for_user
from schemas.auth import UserResponse
from models.staff_members import Staff_members

from conftest import (
    add_product,
    auth_headers,
    make_client_account,
    register_user,
    unique_email,
)

STAFF_URL = "/api/v1/entities/staff_members"


def _as_user(user: dict, email: str | None = None) -> UserResponse:
    return UserResponse(id=user["id"], email=email or user.get("email", ""), name="X", role="user")


async def _link_staff(owner_user_id: str, login_user_id: str, email: str, role: str = "cashier"):
    async with db_manager.async_session_maker() as db:
        row = Staff_members(
            user_id=owner_user_id,
            login_user_id=login_user_id,
            name="Cashier",
            email=email,
            role=role,
            is_active=True,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row.id


@pytest.mark.asyncio
async def test_tenant_scope_resolves_staff_via_fk_not_email(client):
    """A staff login linked by FK resolves to the owning merchant even after the
    login's email no longer matches the staff row's email column."""
    owner, _t, owner_client_id = await make_client_account(client)
    staff_email = unique_email()
    staff_login, _st, _r = await register_user(client, email=staff_email)

    # Link via FK, but deliberately store a *non-matching* email on the staff row
    # to prove resolution does not depend on the email string.
    await _link_staff(owner["id"], staff_login["id"], email="stale-" + staff_email)

    async with db_manager.async_session_maker() as db:
        scope = await resolve_tenant_scope(db, _as_user(staff_login, email=staff_email))

    assert scope.role == "client"
    assert scope.owner_user_id == owner["id"]
    assert scope.client_id == owner_client_id


@pytest.mark.asyncio
async def test_pre_registered_email_is_not_auto_linked(client):
    """The hijack: an attacker pre-registers the email a merchant later adds as
    staff. Provisioning must NOT bind that pre-existing account to the merchant —
    the staff row gets no login FK and the attacker stays in their own tenant."""
    attacker_email = unique_email()
    attacker, _at, _r = await register_user(client, email=attacker_email)

    owner, owner_token, _cid = await make_client_account(client)
    create = await client.post(
        STAFF_URL,
        json={"name": "Cashier", "email": attacker_email, "role": "cashier"},
        headers=auth_headers(owner_token),
    )
    assert create.status_code == 201, create.text

    # The staff row must not have been linked to the attacker's pre-existing login.
    async with db_manager.async_session_maker() as db:
        from sqlalchemy import select

        row = (
            await db.execute(select(Staff_members).where(Staff_members.email == attacker_email))
        ).scalar_one()
    assert row.login_user_id is None

    # And the attacker still resolves to their own least-privilege tenant, NOT the
    # merchant's.
    async with db_manager.async_session_maker() as db:
        scope = await resolve_tenant_scope(db, _as_user(attacker, email=attacker_email))
    assert scope.owner_user_id == attacker["id"]


@pytest.mark.asyncio
async def test_provisioned_staff_login_is_linked_via_fk(client):
    """Creating a staff member with a fresh email provisions a login and binds it
    by FK; the cashier then resolves to the owner's tenant."""
    owner, owner_token, owner_client_id = await make_client_account(client)
    await add_product(owner_client_id, owner["id"], name="Merchant-Widget", quantity=2, price=5.0)

    staff_email = unique_email()
    create = await client.post(
        STAFF_URL,
        json={"name": "Cashier", "email": staff_email, "role": "cashier"},
        headers=auth_headers(owner_token),
    )
    assert create.status_code == 201, create.text

    async with db_manager.async_session_maker() as db:
        from sqlalchemy import select

        row = (
            await db.execute(select(Staff_members).where(Staff_members.email == staff_email))
        ).scalar_one()
    assert row.login_user_id is not None

    # The provisioned login resolves to the owning merchant via the FK.
    async with db_manager.async_session_maker() as db:
        scope = await resolve_tenant_scope(
            db, UserResponse(id=row.login_user_id, email=staff_email, name="Cashier", role="user")
        )
    assert scope.owner_user_id == owner["id"]
    assert scope.client_id == owner_client_id


@pytest.mark.asyncio
async def test_permission_resolver_keys_on_fk(client):
    """``_staff_role_for_user`` resolves a staff role by the login FK; a row that
    only matches by email (no FK) is ignored."""
    owner, _t, _cid = await make_client_account(client)
    staff_email = unique_email()
    staff_login, _st, _r = await register_user(client, email=staff_email)

    await _link_staff(owner["id"], staff_login["id"], email=staff_email, role="cashier")
    async with db_manager.async_session_maker() as db:
        role = await _staff_role_for_user(db, staff_login["id"])
    assert role == "cashier"

    # A second login that merely shares an email with an unlinked staff row must
    # NOT inherit a staff role.
    other_email = unique_email()
    other_login, _ot, _r2 = await register_user(client, email=other_email)
    async with db_manager.async_session_maker() as db:
        row = Staff_members(
            user_id=owner["id"],
            login_user_id=None,
            name="Ghost",
            email=other_email,
            role="manager",
            is_active=True,
        )
        db.add(row)
        await db.commit()
    async with db_manager.async_session_maker() as db:
        role = await _staff_role_for_user(db, other_login["id"])
    assert role is None


def test_migration_backfills_login_user_id_from_email(tmp_path):
    """The SEC-11 migration backfills ``login_user_id`` for an already-migrated
    database by matching the historical staff email to a distinct user."""
    import os

    from sqlalchemy import create_engine, inspect, text

    from alembic import command
    from alembic.config import Config

    ini = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "alembic.ini")
    sync_url = f"sqlite:///{tmp_path / 'sec11.db'}"
    cfg = Config(ini)
    cfg.set_main_option("sqlalchemy.url", sync_url)

    # Bring the DB up to the revision *before* SEC-11, then seed a legacy email link.
    command.upgrade(cfg, "a1c2e3d4f5b6")
    engine = create_engine(sync_url)
    owner_id = "owner-" + uuid.uuid4().hex[:8]
    staff_login_id = "stafflogin-" + uuid.uuid4().hex[:8]
    shared_email = f"cashier_{uuid.uuid4().hex[:8]}@example.com"
    with engine.begin() as conn:
        for uid, email in ((owner_id, f"owner_{uuid.uuid4().hex[:8]}@e.com"), (staff_login_id, shared_email)):
            conn.execute(
                text("INSERT INTO users (id, email, role) VALUES (:id, :email, 'user')"),
                {"id": uid, "email": email},
            )
        conn.execute(
            text(
                "INSERT INTO staff_members (user_id, name, email, role) "
                "VALUES (:owner, 'Cashier', :email, 'cashier')"
            ),
            {"owner": owner_id, "email": shared_email},
        )

    command.upgrade(cfg, "head")

    insp = inspect(engine)
    assert "login_user_id" in {c["name"] for c in insp.get_columns("staff_members")}
    with engine.connect() as conn:
        backfilled = conn.execute(
            text("SELECT login_user_id FROM staff_members WHERE email = :e"),
            {"e": shared_email},
        ).scalar_one()
    engine.dispose()
    assert backfilled == staff_login_id
