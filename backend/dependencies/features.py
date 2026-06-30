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

from core.cache import TTL_FEATURES, cache, feature_key
from core.database import get_db
from dependencies.tenancy import TenantScope, get_tenant_scope
from models.client_features import Client_features

logger = logging.getLogger(__name__)

# Canonical feature keys (IB §3.2). An agent may toggle any of these per client;
# a gated route enforces one via ``require_feature``. Keeping the set here makes
# it the single source of truth shared by the toggle endpoint (which rejects an
# unknown name instead of silently storing a cosmetic switch) and the routes that
# actually gate on it. ``zatca`` is compliance-policy (its enforcement decision is
# tracked separately) and ``omnichannel`` has no routes yet — both are valid keys
# but not yet gated; the rest (email_receipts/sms_receipts/loyalty/restaurant/
# inventory/discounts) are enforced.
FEATURE_KEYS = frozenset(
    {
        "email_receipts",
        "sms_receipts",
        "loyalty",
        "restaurant",
        "inventory",
        "discounts",
        "zatca",
        "omnichannel",
    }
)


async def is_feature_enabled(db: AsyncSession, client_id: int, feature_name: str) -> bool:
    """Return whether ``feature_name`` is enabled for ``client_id`` (default True).

    Cached (M10 / #219): a gated route consults this on every request but the flag
    only changes when an agent toggles it, so the boolean is cached per
    ``(client_id, feature_name)`` and invalidated for the whole client by
    ``invalidate_features`` when ``set_client_feature`` writes. The result is a
    plain bool, so it caches cleanly (``False`` is a real cached value, not a miss).
    """

    async def _load() -> bool:
        result = await db.execute(
            select(Client_features.is_enabled).where(
                Client_features.client_id == client_id,
                Client_features.feature_name == feature_name,
            )
        )
        flag = result.scalar_one_or_none()
        # No row => feature not explicitly disabled => allowed.
        return flag is not False

    return await cache.get_or_load(
        feature_key(client_id, feature_name), TTL_FEATURES, _load
    )


def require_feature(feature_name: str):
    """Build a dependency that 403s when ``feature_name`` is disabled for the client.

    Entitlements belong to the **owning merchant**, not the login identity, so the
    gate resolves the client via the tenant scope (``scope.client_id``) — a staff
    cashier inherits their merchant's feature flags rather than being 403'd for
    having no ``Clients`` row of their own (U0.2). A non-client caller (agent /
    master, ``client_id is None``) is rejected as before.

    Usage::

        @router.post("/loyalty/redeem", dependencies=[Depends(require_feature("loyalty"))])
    """

    async def _dependency(
        scope: TenantScope = Depends(get_tenant_scope),
        db: AsyncSession = Depends(get_db),
    ) -> None:
        if scope.client_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only clients can use this feature",
            )
        if not await is_feature_enabled(db, scope.client_id, feature_name):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"The '{feature_name}' feature is disabled for your account.",
            )

    return _dependency
