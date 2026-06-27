"""Tenancy scope resolution (Phase 1 — deep ``get_tenant_scope`` refactor).

The product has a three-tier tenancy hierarchy (master → agent → client). POS
domain objects (products, customers, transactions, reports, …) are owned by the
**client merchant** and must never leak across tenants. Historically every CRUD
handler scoped by the raw ``user_id`` of the caller. That works for a 1:1
account-per-merchant world, but it is not the *tenancy* model — it breaks the
moment a merchant has more than one login (e.g. a cashier / staff member who
should see the merchant's catalog, not an empty one of their own).

``get_tenant_scope`` centralises that resolution in one place:

* **client merchant**  → scopes to its own ``user_id`` (and exposes ``client_id``)
* **staff member**     → resolves to the *owning client's* ``user_id`` so staff
  share the merchant's catalog/customers/sales rather than a private empty set
* **agent**            → scopes to its own ``user_id`` (exposes ``agent_id``)
* **master**           → unrestricted (``owner_user_id`` is ``None`` ⇒ no filter)

Service-layer filters take ``owner_user_id`` instead of the caller's raw id, so
the *tenancy* boundary — not the login identity — is what isolates data. This is
the single seam where the staff→client mapping lives; the CRUD triads just pass
``scope.owner_user_id`` through.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.auth import get_current_user
from schemas.auth import UserResponse

logger = logging.getLogger(__name__)


@dataclass
class TenantScope:
    """The resolved tenancy boundary for the current request.

    ``owner_user_id`` is the value entity queries should filter on. It is
    ``None`` only for the platform master, who sees everything.
    """

    role: str  # "master" | "agent" | "client"
    user_id: str  # the caller's own user id (login identity)
    owner_user_id: Optional[str]  # the tenancy owner to scope entities by
    client_id: Optional[int] = None
    agent_id: Optional[int] = None

    @property
    def is_master(self) -> bool:
        return self.role == "master"

    @property
    def is_unrestricted(self) -> bool:
        """Master sees all rows; everyone else is owner-scoped."""
        return self.owner_user_id is None


async def resolve_tenant_scope(db: AsyncSession, current_user: UserResponse) -> TenantScope:
    """Resolve the tenancy scope for ``current_user`` from DB membership.

    Mirrors ``routers/tenant.py::get_user_role`` but additionally maps a staff
    member back to the owning client's ``user_id``. Kept import-local to avoid a
    circular import with the tenant router.
    """
    from models.agents import Agents
    from models.clients import Clients
    from models.staff_members import Staff_members
    from models.auth import User

    uid = str(current_user.id)

    # Agent?
    agent = (
        await db.execute(select(Agents).where(Agents.user_id == uid))
    ).scalar_one_or_none()
    if agent:
        return TenantScope(role="agent", user_id=uid, owner_user_id=uid, agent_id=agent.id)

    # Client merchant?
    client = (
        await db.execute(select(Clients).where(Clients.user_id == uid))
    ).scalar_one_or_none()
    if client:
        return TenantScope(
            role="client",
            user_id=uid,
            owner_user_id=uid,
            client_id=client.id,
            agent_id=client.agent_id,
        )

    # Staff member operating under a client merchant? Resolve to the owner so the
    # cashier shares the merchant's catalog/customers/sales rather than an empty
    # private tenant. The staff row's ``user_id`` is the *owning* account, while
    # ``login_user_id`` is the cashier's own login. SEC-11: match on the immutable
    # login FK, never the mutable email — an email match was a tenant boundary an
    # attacker could hijack by pre-registering a soon-to-be-staff address.
    staff = (
        await db.execute(
            select(Staff_members)
            .where(Staff_members.login_user_id == uid)
            .order_by(Staff_members.id.asc())
            .limit(1)
        )
    ).scalars().first()
    if staff and staff.user_id and staff.user_id != uid:
        owner_client = (
            await db.execute(select(Clients).where(Clients.user_id == staff.user_id))
        ).scalar_one_or_none()
        return TenantScope(
            role="client",
            user_id=uid,
            owner_user_id=staff.user_id,
            client_id=owner_client.id if owner_client else None,
            agent_id=owner_client.agent_id if owner_client else None,
        )

    # Explicitly-seeded admins are the platform master (unrestricted).
    user = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
    if user and user.role == "admin":
        return TenantScope(role="master", user_id=uid, owner_user_id=None)

    # Any other account defaults to a least-privilege client scoped to itself.
    return TenantScope(role="client", user_id=uid, owner_user_id=uid)


async def resolve_owner_user_id(db: AsyncSession, user_id: str) -> Optional[str]:
    """Resolve the tenancy-owner id for a raw user id (e.g. a JWT ``sub``).

    Write-path middleware (audit, metering) only has the actor's user id, not a
    full :class:`UserResponse`. This loads the user to recover the email — so a
    staff member maps back to the *owning* merchant — and defers to
    :func:`resolve_tenant_scope`. Returns ``None`` for the platform master
    (unrestricted), and falls back to the caller's own id if the user row cannot
    be loaded. Best-effort: never raises.
    """
    from models.auth import User

    try:
        user = (
            await db.execute(select(User).where(User.id == str(user_id)))
        ).scalar_one_or_none()
        if user is None:
            return str(user_id)
        pseudo = UserResponse(
            id=str(user.id),
            email=(user.email or ""),
            name=(user.name or ""),
            role=(user.role or "user"),
        )
        scope = await resolve_tenant_scope(db, pseudo)
        return scope.owner_user_id
    except Exception:  # pragma: no cover - tagging must not break the write path
        logger.debug("Owner resolution failed for user_id=%s", user_id)
        return str(user_id)


async def get_tenant_scope(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TenantScope:
    """FastAPI dependency exposing the caller's :class:`TenantScope`."""
    return await resolve_tenant_scope(db, current_user)


async def get_owner_id(scope: TenantScope = Depends(get_tenant_scope)) -> str:
    """The tenancy-owner user id the caller's data lives under, as a plain string.

    For a client merchant or agent this is their own id; for a **staff member**
    it is the *owning* merchant's id (so a cashier operates on the merchant's
    catalog/sales, not an empty private tenant — F-SEC-1). Master has no owner
    scope, so we fall back to the caller's own id rather than ``None`` — a master
    hitting an owner-scoped endpoint then acts within its own (empty) scope rather
    than crashing on a ``None`` filter.

    Used by the deep routers (``pos``/``production``) that resolve a ``Clients``
    row or filter by ownership and must keep ``current_user.id`` separately for the
    *actor* identity (audit, cashier-on-shift). The generic CRUD triads use
    ``scope.owner_user_id`` directly instead.
    """
    return scope.owner_user_id or scope.user_id
