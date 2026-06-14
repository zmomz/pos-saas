"""Catalog router — modifier groups, modifiers & combos for ANY merchant (ISSUE-066).

Modifiers/combos (F-056) were built for the restaurant vertical and live behind
the restaurant double-gate (``business_type`` ∈ restaurant/both + the
``restaurant`` feature). They are, however, plain *catalog* primitives: a retail
merchant wants gift-wrap modifiers and bundle combos just as much as a café wants
add-ons and meal deals.

This router re-exposes those same primitives on ``/api/v1/catalog`` behind a
single gate — the caller must be a *client merchant* — with **no** business-type
or feature requirement, so a ``retail`` client (403'd by ``/api/v1/restaurant``)
can build them. It reuses ``RestaurantService`` and the same tables, so a group
or combo defined here is the very same row the sale path reads: a combo sold at
the POS deducts its component stock (ISSUE-032, wired into the retail sale path).
Every read/write is scoped to the caller's ``user_id`` (SEC-02).
"""
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.auth import get_current_user
from models.clients import Clients
from schemas.auth import UserResponse
from services.restaurant import RestaurantService

# Reuse the restaurant router's request/response schemas + combo serializer so the
# catalog surface and the restaurant surface stay byte-for-byte compatible.
from routers.restaurant import (
    ComboData,
    ComboResponse,
    ModifierData,
    ModifierGroupData,
    ModifierGroupResponse,
    ModifierResponse,
    _combo_to_response,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/catalog", tags=["catalog"])


# ---------- Gate dependency ----------
async def get_catalog_client(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Clients:
    """Resolve the caller's client row — the *only* gate on the catalog surface.

    Unlike ``get_restaurant_client`` this enforces **no** ``business_type`` or
    feature flag: modifiers/combos are catalog primitives every business type can
    use (ISSUE-066). A non-client account (master/agent/unknown) still gets 403.
    """
    result = await db.execute(select(Clients).where(Clients.user_id == str(current_user.id)))
    client = result.scalar_one_or_none()
    if client is None:
        raise HTTPException(
            status_code=403, detail="Only client merchants can manage the catalog"
        )
    return client


# ---------- Modifier groups ----------
@router.get("/modifier-groups", response_model=List[ModifierGroupResponse])
async def list_modifier_groups(
    client: Clients = Depends(get_catalog_client),
    db: AsyncSession = Depends(get_db),
):
    """List the caller's modifier groups (ISSUE-066, F-056)."""
    service = RestaurantService(db)
    return await service.list_modifier_groups(user_id=client.user_id)


@router.post("/modifier-groups", response_model=ModifierGroupResponse, status_code=201)
async def create_modifier_group(
    data: ModifierGroupData,
    client: Clients = Depends(get_catalog_client),
    db: AsyncSession = Depends(get_db),
):
    """Create a modifier group (required + min/max rules)."""
    service = RestaurantService(db)
    return await service.create_modifier_group(
        data.model_dump(), user_id=client.user_id, client_id=client.id
    )


@router.delete("/modifier-groups/{group_id}")
async def delete_modifier_group(
    group_id: int,
    client: Clients = Depends(get_catalog_client),
    db: AsyncSession = Depends(get_db),
):
    """Delete a modifier group and its modifiers/attachments (owner-scoped)."""
    service = RestaurantService(db)
    ok = await service.delete_modifier_group(group_id, user_id=client.user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Modifier group not found")
    return {"message": "Modifier group deleted successfully", "id": group_id}


# ---------- Modifiers ----------
@router.get("/modifier-groups/{group_id}/modifiers", response_model=List[ModifierResponse])
async def list_modifiers(
    group_id: int,
    client: Clients = Depends(get_catalog_client),
    db: AsyncSession = Depends(get_db),
):
    """List a group's modifiers (owner-scoped)."""
    service = RestaurantService(db)
    group = await service.get_modifier_group(group_id, user_id=client.user_id)
    if not group:
        raise HTTPException(status_code=404, detail="Modifier group not found")
    return await service.list_modifiers(group_id, user_id=client.user_id)


@router.post("/modifier-groups/{group_id}/modifiers", response_model=ModifierResponse, status_code=201)
async def create_modifier(
    group_id: int,
    data: ModifierData,
    client: Clients = Depends(get_catalog_client),
    db: AsyncSession = Depends(get_db),
):
    """Add a modifier (bilingual name + price delta) to a group."""
    service = RestaurantService(db)
    modifier = await service.create_modifier(
        group_id, data.model_dump(), user_id=client.user_id, client_id=client.id
    )
    if modifier is None:
        raise HTTPException(status_code=404, detail="Modifier group not found")
    return modifier


# ---------- Product ↔ modifier-group attachment ----------
@router.get("/products/{product_id}/modifier-groups")
async def list_product_modifier_groups(
    product_id: int,
    client: Clients = Depends(get_catalog_client),
    db: AsyncSession = Depends(get_db),
):
    """List the modifier groups (with their modifiers) attached to a product."""
    service = RestaurantService(db)
    groups = await service.list_product_groups(product_id, user_id=client.user_id)
    return {"items": groups, "total": len(groups)}


@router.post("/products/{product_id}/modifier-groups/{group_id}", status_code=201)
async def attach_modifier_group(
    product_id: int,
    group_id: int,
    client: Clients = Depends(get_catalog_client),
    db: AsyncSession = Depends(get_db),
):
    """Attach a modifier group to a product (idempotent, owner-scoped)."""
    service = RestaurantService(db)
    link = await service.attach_group_to_product(
        product_id, group_id, user_id=client.user_id, client_id=client.id
    )
    if link is None:
        raise HTTPException(status_code=404, detail="Product or modifier group not found")
    return {"message": "Modifier group attached", "product_id": product_id, "group_id": group_id}


@router.delete("/products/{product_id}/modifier-groups/{group_id}")
async def detach_modifier_group(
    product_id: int,
    group_id: int,
    client: Clients = Depends(get_catalog_client),
    db: AsyncSession = Depends(get_db),
):
    """Detach a modifier group from a product (owner-scoped)."""
    service = RestaurantService(db)
    ok = await service.detach_group_from_product(product_id, group_id, user_id=client.user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Attachment not found")
    return {"message": "Modifier group detached", "product_id": product_id, "group_id": group_id}


# ---------- Combos ----------
@router.get("/combos", response_model=List[ComboResponse])
async def list_combos(
    client: Clients = Depends(get_catalog_client),
    db: AsyncSession = Depends(get_db),
):
    """List the caller's combos with each one's component sum."""
    service = RestaurantService(db)
    combos = await service.list_combos(user_id=client.user_id)
    return [await _combo_to_response(service, c, client.user_id) for c in combos]


@router.post("/combos", response_model=ComboResponse, status_code=201)
async def create_combo(
    data: ComboData,
    client: Clients = Depends(get_catalog_client),
    db: AsyncSession = Depends(get_db),
):
    """Create a combo — components + a bundle price that overrides their sum."""
    service = RestaurantService(db)
    combo = await service.create_combo(
        data.model_dump(), user_id=client.user_id, client_id=client.id
    )
    return await _combo_to_response(service, combo, client.user_id)


@router.delete("/combos/{combo_id}")
async def delete_combo(
    combo_id: int,
    client: Clients = Depends(get_catalog_client),
    db: AsyncSession = Depends(get_db),
):
    """Delete a combo (owner-scoped)."""
    service = RestaurantService(db)
    ok = await service.delete_combo(combo_id, user_id=client.user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Combo not found")
    return {"message": "Combo deleted successfully", "id": combo_id}
