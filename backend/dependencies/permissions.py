"""Granular permission enforcement (Phase 3 — SRS permissions).

The ``permissions`` table stores per-user grant/deny rows (``permission_key`` +
``is_granted``). Before this module those rows were stored but never enforced.
``require_permission`` turns a key into an enforced gate a route can depend on.

Semantics — **grant by default, explicit deny wins** (mirrors
``dependencies.features.require_feature`` so the two behave consistently):

* The platform **master** (``role == "admin"``) bypasses all permission checks.
* Otherwise the caller is allowed **unless** an explicit ``is_granted = False``
  row exists for ``(user_id, permission_key)``.

This keeps account owners (client/agent) and existing flows working out of the
box, while letting an operator revoke a specific capability (e.g. ``pos.refund``)
from a sub-account by writing a deny row. To run a stricter deny-by-default
policy for a key, seed an explicit deny and grant it only where wanted.
"""
import logging

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.auth import get_current_user
from models.permissions import Permissions
from schemas.auth import UserResponse

logger = logging.getLogger(__name__)


async def has_permission(db: AsyncSession, user_id: str, permission_key: str) -> bool:
    """Return whether ``user_id`` is allowed to use ``permission_key``."""
    result = await db.execute(
        select(Permissions.is_granted).where(
            Permissions.user_id == str(user_id),
            Permissions.permission_key == permission_key,
        )
    )
    flag = result.scalar_one_or_none()
    # No row => not explicitly denied => allowed.
    return flag is not False


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
