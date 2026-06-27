"""Granular permission enforcement (Phase 3 — SRS permissions).

The ``permissions`` table stores per-user override rows (``permission_key`` +
``is_granted``). ``require_permission`` turns a key into an enforced gate a route
can depend on; ``has_permission`` is the resolver behind it.

Resolution order for ``has_permission(db, user_id, key)``:

1. **Explicit override wins.** A ``Permissions`` row for ``(user_id, key)`` is
   honoured verbatim — an explicit deny revokes a capability, an explicit grant
   restores one — so an operator can tune an individual login either way.
2. **Otherwise the staff role default applies (ISSUE-034).** A logged-in *staff
   member* (resolved by matching their login email to a ``Staff_members`` row)
   is allowed a **managed** key (``pos.refund`` / ``pos.void`` / ``pos.discount``
   / ``pos.price_override``) only where :data:`ROLE_PERMISSIONS` grants it to
   their role. A cashier is denied these by default; a manager/admin is allowed.
3. **Everyone else keeps grant-by-default.** Account owners (client/agent) and
   the platform **master** (``role == "admin"``, also short-circuited in
   ``require_permission``) are not staff sub-accounts, so they retain every
   capability unless an explicit deny row revokes it. Non-managed keys are
   likewise allowed by default for everyone.

This means a real merchant's staff get permissions enforced *by role* out of the
box — the prior behaviour only ever denied hand-seeded deny rows (H12).
"""
import logging
from typing import Optional

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.auth import get_current_user
from models.permissions import Permissions
from schemas.auth import UserResponse

logger = logging.getLogger(__name__)


# ---- Role → permission default map (ISSUE-034, H12) -------------------------
# "Managed" keys are the sensitive POS capabilities gated by staff role. Any key
# outside this set stays grant-by-default for staff too, so the map only ever
# tightens the sensitive surface rather than silently denying unrelated keys.
MANAGED_PERMISSION_KEYS = frozenset(
    {"pos.refund", "pos.void", "pos.discount", "pos.price_override"}
)

# The default capabilities each staff role grants. A role absent from the map is
# treated as the least-privilege "cashier" (basic sale only). "admin" here is the
# staff-level role (owner-equivalent operator), distinct from the platform master
# ``User.role == "admin"`` which bypasses checks entirely.
ROLE_PERMISSIONS: dict[str, frozenset] = {
    "cashier": frozenset(),
    "manager": MANAGED_PERMISSION_KEYS,
    "admin": MANAGED_PERMISSION_KEYS,
}


def role_allows(role: str, permission_key: str) -> bool:
    """Whether a staff ``role`` grants ``permission_key`` by default.

    Unmanaged keys are always allowed; a managed key is allowed only when the
    role's default grant set includes it. An unknown role falls back to the
    least-privilege ``cashier`` defaults.
    """
    if permission_key not in MANAGED_PERMISSION_KEYS:
        return True
    granted = ROLE_PERMISSIONS.get(role, ROLE_PERMISSIONS["cashier"])
    return permission_key in granted


async def _staff_role_for_user(db: AsyncSession, user_id: str) -> Optional[str]:
    """Resolve a login to its staff role, or ``None`` if it is not a sub-account.

    A staff member's login is bound to a ``Staff_members`` row by the immutable
    ``login_user_id`` FK (SEC-11), whose ``user_id`` is the *owning* merchant (the
    same mapping tenancy uses). Matching the FK — not the mutable email — keeps a
    pre-registered-email attacker from inheriting a staff role. If the matched row
    belongs to the caller themselves (``staff.user_id == user_id``) the account is
    the owner, not a staff sub-account, and keeps grant-by-default.
    """
    from models.staff_members import Staff_members

    # ``login_user_id`` is not unique, so resolve to the first match rather than
    # ``scalar_one_or_none`` (which would raise on any duplicate) — permission
    # resolution must never break the request.
    staff = (
        await db.execute(
            select(Staff_members)
            .where(Staff_members.login_user_id == str(user_id))
            .order_by(Staff_members.id.asc())
            .limit(1)
        )
    ).scalars().first()
    if staff is None or staff.user_id == str(user_id):
        return None
    return staff.role


async def has_permission(db: AsyncSession, user_id: str, permission_key: str) -> bool:
    """Return whether ``user_id`` is allowed to use ``permission_key``.

    See the module docstring for the resolution order: explicit override →
    staff-role default → grant-by-default.
    """
    result = await db.execute(
        select(Permissions.is_granted).where(
            Permissions.user_id == str(user_id),
            Permissions.permission_key == permission_key,
        )
    )
    flag = result.scalar_one_or_none()
    if flag is not None:
        # Explicit per-user override (deny or grant) wins over the role default.
        return flag

    # No override: a staff sub-account is gated by its role; anyone else (owner /
    # agent / master / non-staff) keeps grant-by-default.
    role = await _staff_role_for_user(db, str(user_id))
    if role is None:
        return True
    return role_allows(role, permission_key)


async def get_effective_permissions(db: AsyncSession, current_user: UserResponse) -> dict:
    """Return the caller's explicit permission grants/denies as a map.

    Consumed by ``GET /api/v1/auth/me/permissions`` so the frontend can
    hide/disable actions the user lacks (permission-aware UI).
    """
    if current_user.role == "admin":
        return {"is_master": True, "denied": [], "granted": []}
    result = await db.execute(
        select(Permissions.permission_key, Permissions.is_granted).where(
            Permissions.user_id == str(current_user.id)
        )
    )
    denied, granted = [], []
    for key, is_granted in result.all():
        (granted if is_granted else denied).append(key)
    return {"is_master": False, "denied": denied, "granted": granted}


def require_permission(permission_key: str):
    """Build a dependency that 403s when ``permission_key`` is denied for the caller.

    Usage::

        @router.post("/refund", dependencies=[Depends(require_permission("pos.refund"))])
    """

    async def _dependency(
        current_user: UserResponse = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> None:
        # Platform master bypasses permission gates entirely.
        if current_user.role == "admin":
            return
        if not await has_permission(db, str(current_user.id), permission_key):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"You do not have the '{permission_key}' permission.",
            )

    return _dependency
