"""Platform-settings service (M10 Admin, #225).

Read/write helpers over the ``platform_settings`` key/value table, plus the
typed accessor the maintenance-mode slice needs. Values are JSON-encoded so a
setting can be a scalar or a small object; a missing row reads as ``None``.

The maintenance state is deliberately read **through** the DB on demand rather
than memoised in the process: the flag is authoritative in one place (the row),
so a toggle on one worker is seen by every worker on its next check, and the
test suite's per-test table wipe can never leave a stale "enabled" cached in
memory (there is no in-memory copy to go stale).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import db_manager
from models.platform_settings import PlatformSetting

logger = logging.getLogger(__name__)

MAINTENANCE_KEY = "maintenance_mode"


async def get_setting(db: AsyncSession, key: str) -> Optional[Any]:
    """Return the JSON-decoded value for ``key`` (or ``None`` if unset)."""
    row = (await db.execute(select(PlatformSetting).where(PlatformSetting.key == key))).scalar_one_or_none()
    if row is None or row.value is None:
        return None
    try:
        return json.loads(row.value)
    except (TypeError, ValueError):
        return None


async def set_setting(db: AsyncSession, key: str, value: Any, updated_by: Optional[str] = None) -> None:
    """Upsert ``key`` to the JSON-encoded ``value`` (single row per key)."""
    row = (await db.execute(select(PlatformSetting).where(PlatformSetting.key == key))).scalar_one_or_none()
    encoded = json.dumps(value)
    if row is None:
        db.add(PlatformSetting(key=key, value=encoded, updated_by=updated_by, updated_at=datetime.now()))
    else:
        row.value = encoded
        row.updated_by = updated_by
        row.updated_at = datetime.now()
    await db.commit()


def _normalize_maintenance(value: Any) -> dict:
    """Coerce a stored maintenance value into a stable ``{enabled, message}`` dict."""
    if isinstance(value, dict):
        return {"enabled": bool(value.get("enabled")), "message": value.get("message")}
    # Legacy/scalar form: a bare truthy value means "on" with no message.
    return {"enabled": bool(value), "message": None}


async def get_maintenance_state(db: AsyncSession) -> dict:
    """Return the current maintenance state as ``{enabled, message}`` (off by default)."""
    return _normalize_maintenance(await get_setting(db, MAINTENANCE_KEY))


async def set_maintenance_state(
    db: AsyncSession, enabled: bool, message: Optional[str] = None, updated_by: Optional[str] = None
) -> dict:
    """Persist and return the maintenance state."""
    state = {"enabled": bool(enabled), "message": message}
    await set_setting(db, MAINTENANCE_KEY, state, updated_by=updated_by)
    return state


async def is_maintenance_enabled() -> bool:
    """Cheap standalone check for middleware — opens its own short-lived session.

    Best-effort: any error (e.g. the table not yet migrated) reads as *off* so a
    settings-layer hiccup can never take the whole API down.
    """
    try:
        async with db_manager.async_session_maker() as db:
            return (await get_maintenance_state(db))["enabled"]
    except Exception:  # pragma: no cover - never let the gate fail closed
        logger.debug("maintenance check failed; treating as disabled")
        return False
