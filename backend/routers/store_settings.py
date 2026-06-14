"""Merchant store-settings screen (ISSUE-079).

One screen / endpoint for the store-level identity + operational defaults that
feed every receipt and invoice: the VAT and Commercial-Registration (CR) numbers,
the receipt footer line, the branch profile (address / city / phone) and the
business hours.

The seller name (``clients.business_name``) and VAT number (``clients.vat_number``)
are the fiscally-authoritative fields the existing receipt / invoice / ZATCA paths
already read, so this screen writes them through to the ``clients`` row. The
remaining fields live on the dedicated ``store_settings`` row keyed by the tenancy
owner. A staff member resolves to the *owning* merchant's scope, so a cashier sees
and edits the merchant's store settings rather than a private empty set.
"""
import json
import logging
from typing import Any, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.tenancy import TenantScope, get_tenant_scope
from models.clients import Clients
from services.store_settings import get_store_settings, upsert_store_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/store-settings", tags=["store-settings"])


class StoreSettingsResponse(BaseModel):
    """The merged store-settings view shown on the merchant screen."""

    store_name: Optional[str] = None
    vat_number: Optional[str] = None
    cr_number: Optional[str] = None
    receipt_footer: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    phone: Optional[str] = None
    business_hours: Optional[List[Any]] = None


class StoreSettingsUpdate(BaseModel):
    """Partial update — only the provided fields are changed."""

    store_name: Optional[str] = None
    vat_number: Optional[str] = None
    cr_number: Optional[str] = None
    receipt_footer: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    phone: Optional[str] = None
    business_hours: Optional[List[Any]] = None


async def _get_client(db: AsyncSession, owner_user_id: Optional[str]) -> Optional[Clients]:
    if not owner_user_id:
        return None
    result = await db.execute(select(Clients).where(Clients.user_id == str(owner_user_id)))
    return result.scalar_one_or_none()


def _parse_hours(raw: Optional[str]) -> Optional[List[Any]]:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


def _merged(client: Optional[Clients], settings) -> StoreSettingsResponse:
    return StoreSettingsResponse(
        store_name=(client.business_name if client else None),
        vat_number=(client.vat_number if client else None),
        cr_number=(settings.cr_number if settings else None),
        receipt_footer=(settings.receipt_footer if settings else None),
        address=(settings.address if settings else None),
        city=(settings.city if settings else None),
        phone=(settings.phone if settings else None),
        business_hours=_parse_hours(settings.business_hours if settings else None),
    )


@router.get("", response_model=StoreSettingsResponse)
async def get_settings(
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Return the merchant's store settings (seller name + VAT from the client
    row, the rest from the store_settings row), defaulting to empty fields when
    nothing has been saved yet."""
    owner_id = scope.owner_user_id or scope.user_id
    client = await _get_client(db, owner_id)
    settings = await get_store_settings(db, owner_id)
    return _merged(client, settings)


@router.put("", response_model=StoreSettingsResponse)
async def update_settings(
    payload: StoreSettingsUpdate,
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Persist the merchant's store settings.

    ``store_name`` / ``vat_number`` are written through to the authoritative
    ``clients`` row so the existing receipt / invoice / ZATCA paths reflect the
    edit; the remaining fields are upserted onto the ``store_settings`` row.
    """
    owner_id = scope.owner_user_id or scope.user_id
    client = await _get_client(db, owner_id)

    # Write the fiscally-authoritative fields through to the client row.
    if client is not None:
        if payload.store_name is not None:
            client.business_name = payload.store_name
        if payload.vat_number is not None:
            client.vat_number = payload.vat_number

    business_hours = (
        json.dumps(payload.business_hours, ensure_ascii=False)
        if payload.business_hours is not None
        else None
    )
    settings = await upsert_store_settings(
        db,
        owner_id,
        cr_number=payload.cr_number,
        receipt_footer=payload.receipt_footer,
        address=payload.address,
        city=payload.city,
        phone=payload.phone,
        business_hours=business_hours,
    )
    await db.commit()
    await db.refresh(settings)
    if client is not None:
        await db.refresh(client)
    return _merged(client, settings)
