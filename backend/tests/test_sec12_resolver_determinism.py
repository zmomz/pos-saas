"""SEC-12: tenancy resolvers must be deterministic and agree on duplicate rows.

``resolve_tenant_scope`` used ``scalar_one_or_none()`` for the agent / client /
owning-client lookups, which raises (a 500) the moment a login has more than one
matching row — a data-integrity drift that should degrade gracefully, not crash
the request. The permission resolver, post-SEC-11, already resolves the staff
lookup deterministically (``order_by(id).limit(1)``). These tests pin the two
remaining behaviours of the audit acceptance criteria:

* a duplicate (client / agent / owning-client) row resolves *deterministically*
  to the lowest-id row instead of 500-ing;
* both resolvers *agree* on whether a login is a staff sub-account and of whom.
"""
import uuid

import pytest
from sqlalchemy import select

from core.database import db_manager
from dependencies.permissions import _staff_role_for_user
from dependencies.tenancy import resolve_tenant_scope
from models.agents import Agents
from models.clients import Clients
from models.staff_members import Staff_members
from schemas.auth import UserResponse

from conftest import make_agent_account, make_client_account, register_user, unique_email


def _as_user(user: dict, email: str | None = None) -> UserResponse:
    return UserResponse(id=user["id"], email=email or user.get("email", ""), name="X", role="user")


async def _add_client_row(user_id: str, agent_id: int) -> int:
    async with db_manager.async_session_maker() as db:
        row = Clients(
            user_id=user_id,
            agent_id=agent_id,
            business_name="Dup Shop",
            email=unique_email(),
            is_active=True,
            invoice_counter=0,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row.id


async def _add_agent_row(user_id: str) -> int:
    async with db_manager.async_session_maker() as db:
        row = Agents(
            user_id=user_id,
            company_name="Dup Agent",
            email=unique_email(),
            package_type=1,
            used_slots=0,
            is_active=True,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row.id


async def _link_staff(owner_user_id: str, login_user_id: str, role: str = "cashier") -> int:
    async with db_manager.async_session_maker() as db:
        row = Staff_members(
            user_id=owner_user_id,
            login_user_id=login_user_id,
            name="Cashier",
            email=unique_email(),
            role=role,
            is_active=True,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row.id


@pytest.mark.asyncio
async def test_duplicate_client_rows_resolve_deterministically(client):
    """A login owning two ``Clients`` rows resolves (no 500) to the lowest-id row."""
    owner, _t, first_client_id = await make_client_account(client)

    async with db_manager.async_session_maker() as db:
        existing = (
            await db.execute(select(Clients).where(Clients.user_id == owner["id"]))
        ).scalars().first()
        agent_id = existing.agent_id
    second_client_id = await _add_client_row(owner["id"], agent_id)
    assert second_client_id != first_client_id

    async with db_manager.async_session_maker() as db:
        scope = await resolve_tenant_scope(db, _as_user(owner))

    assert scope.role == "client"
    assert scope.owner_user_id == owner["id"]
    # Deterministic: the lowest id wins, regardless of insertion race.
    assert scope.client_id == min(first_client_id, second_client_id)


@pytest.mark.asyncio
async def test_duplicate_agent_rows_resolve_deterministically(client):
    """A login owning two ``Agents`` rows resolves (no 500) to the lowest-id row."""
    agent_user, _t, first_agent_id = await make_agent_account(client)
    second_agent_id = await _add_agent_row(agent_user["id"])
    assert second_agent_id != first_agent_id

    async with db_manager.async_session_maker() as db:
        scope = await resolve_tenant_scope(db, _as_user(agent_user))

    assert scope.role == "agent"
    assert scope.owner_user_id == agent_user["id"]
    assert scope.agent_id == min(first_agent_id, second_agent_id)


@pytest.mark.asyncio
async def test_staff_owner_with_duplicate_client_rows_resolves_deterministically(client):
    """A staff login whose owner has duplicate ``Clients`` rows resolves (no 500)
    to that owner, picking the lowest-id owning client."""
    owner, _t, first_client_id = await make_client_account(client)
    async with db_manager.async_session_maker() as db:
        existing = (
            await db.execute(select(Clients).where(Clients.user_id == owner["id"]))
        ).scalars().first()
        agent_id = existing.agent_id
    second_client_id = await _add_client_row(owner["id"], agent_id)

    staff_login, _st, _r = await register_user(client)
    await _link_staff(owner["id"], staff_login["id"])

    async with db_manager.async_session_maker() as db:
        scope = await resolve_tenant_scope(db, _as_user(staff_login))

    assert scope.role == "client"
    assert scope.owner_user_id == owner["id"]
    assert scope.client_id == min(first_client_id, second_client_id)


@pytest.mark.asyncio
async def test_resolvers_agree_on_staff_membership(client):
    """Both resolvers agree on whether a login is a staff sub-account.

    A linked staff login: tenancy maps it to the *owner* (not itself) and the
    permission resolver returns its role. The owner's own login: tenancy maps it
    to itself and the permission resolver returns ``None`` (not a sub-account)."""
    owner, _t, _cid = await make_client_account(client)
    staff_login, _st, _r = await register_user(client)
    await _link_staff(owner["id"], staff_login["id"], role="manager")

    async with db_manager.async_session_maker() as db:
        staff_scope = await resolve_tenant_scope(db, _as_user(staff_login))
        staff_role = await _staff_role_for_user(db, staff_login["id"])
        owner_scope = await resolve_tenant_scope(db, _as_user(owner))
        owner_role = await _staff_role_for_user(db, owner["id"])

    # Agree the staff login is a sub-account of the owner.
    assert staff_scope.owner_user_id == owner["id"]
    assert staff_scope.owner_user_id != staff_login["id"]
    assert staff_role == "manager"

    # Agree the owner's own login is NOT a staff sub-account.
    assert owner_scope.owner_user_id == owner["id"]
    assert owner_role is None
