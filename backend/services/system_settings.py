"""Helpers for the platform-wide ``system_settings`` key/value store.

The only setting modelled so far is the **global VAT rate** (SRS MA-05): the
master sets it once and every agent/client inherits it — they cannot override it
per-product or per-sale. ``get_global_tax_rate`` is the single source of truth
the POS uses when pricing a sale.
"""
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.cache import TTL_TAX, cache, tax_global_key
from models.system_settings import System_settings

logger = logging.getLogger(__name__)

# Key under which the global VAT percentage is stored.
GLOBAL_TAX_RATE_KEY = "global_tax_rate"
# Statutory KSA standard rate; used when the master has not set a global rate.
DEFAULT_TAX_RATE = 15.0


async def get_setting(db: AsyncSession, key: str) -> Optional[str]:
    """Return the raw string value for ``key``, or ``None`` if unset."""
    result = await db.execute(
        select(System_settings.value).where(System_settings.key == key)
    )
    return result.scalar_one_or_none()


async def set_setting(db: AsyncSession, key: str, value: str) -> None:
    """Upsert ``key`` = ``value``. Caller is responsible for committing."""
    result = await db.execute(
        select(System_settings).where(System_settings.key == key)
    )
    row = result.scalar_one_or_none()
    if row is None:
        db.add(System_settings(key=key, value=value))
    else:
        row.value = value


async def get_global_tax_rate(db: AsyncSession) -> Optional[float]:
    """Return the master-configured global VAT rate, or ``None`` if not set.

    ``None`` means "no global rate configured" — callers should then fall back to
    their own default (``DEFAULT_TAX_RATE``) so behaviour is unchanged for fresh
    installs.

    Cached (M10 / #219): this resolves on every priced sale but the master sets it
    rarely, so the answer is fronted by the tenant-scoped cache and invalidated by
    ``invalidate_tax`` when the master writes a new rate. The "not set" state is
    cached too (as ``{"rate": None}``) so a fresh install doesn't hit the DB on
    every sale; ``None`` itself is never stored, since it reads as a cache miss.
    """

    async def _load() -> dict:
        raw = await get_setting(db, GLOBAL_TAX_RATE_KEY)
        if raw is None or raw == "":
            return {"rate": None}
        try:
            return {"rate": float(raw)}
        except (TypeError, ValueError):
            logger.warning("Stored global_tax_rate %r is not numeric; ignoring", raw)
            return {"rate": None}

    payload = await cache.get_or_load(tax_global_key(), TTL_TAX, _load)
    rate = payload.get("rate") if isinstance(payload, dict) else None
    return float(rate) if rate is not None else None


async def get_effective_tax_rate(db: AsyncSession, requested: Optional[float] = None) -> float:
    """Resolve the VAT rate to apply.

    Precedence (MA-05 — agents/clients cannot override the global rate):
      1. The master's global rate, if configured.
      2. The caller's ``requested`` rate (legacy/per-request behaviour).
      3. ``DEFAULT_TAX_RATE``.
    """
    global_rate = await get_global_tax_rate(db)
    if global_rate is not None:
        return global_rate
    if requested is not None:
        return requested
    return DEFAULT_TAX_RATE
