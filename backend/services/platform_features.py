"""Platform feature-flag service (M10 Admin, #225).

Platform-**global** feature flags the operator console can edit — kill switches
and rollout toggles that belong to the platform itself, not to any one tenant
(that is what per-client ``client_features`` / :mod:`dependencies.features` are
for). They persist in the shared ``platform_settings`` key/value table under a
single ``feature_flags`` key holding a ``{name: bool}`` override map, so no new
table or migration is needed as the registry grows.

"No fabricated state" (the #225 acceptance): the console never invents flags. The
declared :data:`PLATFORM_FEATURE_FLAGS` registry is the single source of truth for
which flags exist and their defaults; a read returns each declared flag merged
with its persisted override, and a write of an undeclared flag is refused. So the
console only ever shows and stores real, enforceable switches.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from core.database import db_manager
from services.platform_settings import get_setting, set_setting

logger = logging.getLogger(__name__)

FEATURE_FLAGS_KEY = "feature_flags"

# Declared registry: flag name -> {default, description}. The single source of
# truth for what the console may show/store. ``self_registration`` is enforced
# today (gates /auth/register); the rest are declared rollout switches for
# platform capabilities already on the roadmap (#228 AI, #229 analytics), so the
# console reflects real planned behaviour rather than cosmetic toggles.
PLATFORM_FEATURE_FLAGS: dict[str, dict] = {
    "self_registration": {
        "default": True,
        "description": "Allow self-serve tenant registration at /auth/register.",
    },
    "advanced_analytics": {
        "default": False,
        "description": "Expose the advanced-analytics surfaces (CLV, cohort, heatmaps).",
    },
    "ai_assistant": {
        "default": False,
        "description": "Enable the in-app AI assistant and smart-reorder suggestions.",
    },
}


def _overrides_from(value) -> dict:
    """Coerce the stored override blob into a ``{name: bool}`` dict."""
    return value if isinstance(value, dict) else {}


async def get_feature_flags(db: AsyncSession) -> list[dict]:
    """Return every declared flag merged with its persisted override.

    Each entry is ``{key, enabled, description}``. A flag with no stored override
    reads at its declared default — nothing is fabricated, the shape is stable.
    """
    overrides = _overrides_from(await get_setting(db, FEATURE_FLAGS_KEY))
    flags = []
    for key, meta in PLATFORM_FEATURE_FLAGS.items():
        enabled = bool(overrides[key]) if key in overrides else bool(meta["default"])
        flags.append({"key": key, "enabled": enabled, "description": meta["description"]})
    return flags


async def set_feature_flag(
    db: AsyncSession, key: str, enabled: bool, updated_by: Optional[str] = None
) -> dict:
    """Persist a single declared flag; refuse an undeclared name (``KeyError``)."""
    if key not in PLATFORM_FEATURE_FLAGS:
        raise KeyError(key)
    overrides = _overrides_from(await get_setting(db, FEATURE_FLAGS_KEY))
    overrides[key] = bool(enabled)
    await set_setting(db, FEATURE_FLAGS_KEY, overrides, updated_by=updated_by)
    return {"key": key, "enabled": bool(enabled), "description": PLATFORM_FEATURE_FLAGS[key]["description"]}


async def is_platform_feature_enabled(db: AsyncSession, key: str) -> bool:
    """Whether a declared platform flag is on (default applied; unknown ⇒ off)."""
    overrides = _overrides_from(await get_setting(db, FEATURE_FLAGS_KEY))
    if key in overrides:
        return bool(overrides[key])
    meta = PLATFORM_FEATURE_FLAGS.get(key)
    return bool(meta["default"]) if meta else False
