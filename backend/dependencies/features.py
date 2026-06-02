"""Per-client feature-flag enforcement (SRS AG-03).

Agents can toggle individual features on/off for each of their clients
(``client_features`` rows). Before this module those flags were stored but never
checked. ``require_feature`` turns a flag into an enforced gate that a route can
depend on.

Semantics: a feature is **enabled by default**. It is only blocked when an
explicit ``client_features`` row exists for the caller's client with
``is_enabled = False``. This keeps existing clients (no rows) fully functional
while letting an agent disable a capability for a specific client.
"""
import logging

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.auth import get_current_user
from models.client_features import Client_features
from models.clients import Clients
from schemas.auth import UserResponse

logger = logging.getLogger(__name__)


async def is_feature_enabled(db: AsyncSession, client_id: int, feature_name: str) -> bool:
    """Return whether ``feature_name`` is enabled for ``client_id`` (default True)."""
    result = await db.execute(
        select(Client_features.is_enabled).where(
            Client_features.client_id == client_id,
            Client_features.feature_name == feature_name,
        )
    )
    flag = result.scalar_one_or_none()
    # No row => feature not explicitly disabled => allowed.
    return flag is not False


async def _client_id_for_user(db: AsyncSession, user_id: str) -> int:
    result = await db.execute(select(Clients.id).where(Clients.user_id == str(user_id)))
    client_id = result.scalar_one_or_none()
    if client_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only clients can use this feature")
    return client_id


def require_feature(feature_name: str):
    """Build a dependency that 403s when ``feature_name`` is disabled for the client.

    Usage::

        @router.post("/loyalty/redeem", dependencies=[Depends(require_feature("loyalty"))])
    """

    async def _dependency(
        current_user: UserResponse = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> None:
        client_id = await _client_id_for_user(db, str(current_user.id))
        if not await is_feature_enabled(db, client_id, feature_name):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"The '{feature_name}' feature is disabled for your account.",
            )

    return _dependency
