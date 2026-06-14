"""Service helpers for the per-merchant ``store_settings`` row (ISSUE-079).

A merchant's store-level settings are split across two sources of truth:

* the fiscally-authoritative seller name + VAT number on the ``clients`` row
  (already feeding the receipt / invoice / ZATCA paths), and
* the remaining merchant-level fields (CR number, receipt footer, branch
  profile, business hours) on a dedicated :class:`StoreSettings` row keyed by the
  tenancy owner.

These helpers own the second table; the router merges in the ``clients`` fields
for the screen and writes them through on save.
"""
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.store_settings import StoreSettings

logger = logging.getLogger(__name__)

# Fields stored on the dedicated store_settings row (not the clients row).
_SETTINGS_FIELDS = ("cr_number", "receipt_footer", "address", "city", "phone", "business_hours")


async def get_store_settings(db: AsyncSession, owner_user_id: str) -> Optional[StoreSettings]:
    """Return the merchant's ``store_settings`` row, or ``None`` if never saved."""
    if not owner_user_id:
        return None
    result = await db.execute(
        select(StoreSettings).where(StoreSettings.owner_user_id == str(owner_user_id))
    )
    return result.scalar_one_or_none()


async def upsert_store_settings(db: AsyncSession, owner_user_id: str, **fields) -> StoreSettings:
    """Upsert (creating on first save) the merchant's ``store_settings`` row.

    Only the provided fields are touched; a field omitted (``None`` not passed)
    leaves the stored value unchanged. Caller is responsible for committing.
    """
    row = await get_store_settings(db, owner_user_id)
    if row is None:
        row = StoreSettings(owner_user_id=str(owner_user_id))
        db.add(row)

    for field in _SETTINGS_FIELDS:
        if field in fields and fields[field] is not None:
            setattr(row, field, fields[field])
    return row
