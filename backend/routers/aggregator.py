"""Aggregator router — Deliverect-class delivery middleware connector (F-060).

Mounts at ``/api/v1/aggregator``. Brings delivery-aggregator orders (Jahez /
HungerStation) into the POS through a **Deliverect / Delivery-Hero-POS-partner
middleware** (the SRS forbids direct aggregator APIs). Each ingested order
materializes a tableless order ticket **fired to the KDS** (F-057/F-058) and books a
real **ZATCA sale via the shared sale core** (slice 06) that decrements the same
shared stock as an in-store sale.

Surfaces:
- ``POST /connect``                 — a restaurant client registers their middleware
  location id (+ optional webhook secret). Owner-scoped, behind the restaurant
  double-gate.
- ``GET  /connection``              — read the current connection status.
- ``POST /{provider}/webhook``      — **unauthenticated** (the middleware is the
  caller). Routed to the owning client by location id, signature-verified when a
  secret is set, then ingested. Acks 200 even when ignored so the middleware does
  not retry forever; only a bad signature returns 401.

``provider`` is one of ``deliverect`` / ``delivery_hero`` and is recorded on the
``channel_orders`` row, which also enforces idempotency on
``(provider, external_order_id, client_id)``.
"""
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.features import is_feature_enabled
from models.clients import Clients
from routers.restaurant import RESTAURANT_BUSINESS_TYPES, get_restaurant_client
from services.aggregator import (
    PROVIDERS,
    extract_location,
    ingest_aggregator_order,
    verify_aggregator_signature,
)
from services.system_settings import get_effective_tax_rate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/aggregator", tags=["aggregator"])


# ---------- Schemas ----------
class AggregatorConnectRequest(BaseModel):
    location_id: str
    webhook_secret: Optional[str] = None


class AggregatorConnectionResponse(BaseModel):
    connected: bool
    location_id: Optional[str] = None
    webhook_secret_set: bool = False


# ---------- Connect a middleware location (F-060) ----------
@router.post("/connect", response_model=AggregatorConnectionResponse)
async def connect_aggregator(
    body: AggregatorConnectRequest,
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """Register (or update) the caller's aggregator-middleware connection.

    The ``location_id`` routes incoming webhooks to this client, so it must be unique
    across merchants — a value already claimed by another client is rejected 409.
    Behind the restaurant double-gate (aggregator ingest is a restaurant feature).
    """
    location_id = (body.location_id or "").strip()
    if not location_id:
        raise HTTPException(status_code=400, detail="location_id is required")

    clash = (
        await db.execute(
            select(Clients.id).where(
                Clients.aggregator_location_id == location_id,
                Clients.id != client.id,
            )
        )
    ).scalar_one_or_none()
    if clash is not None:
        raise HTTPException(
            status_code=409,
            detail="This aggregator location is already connected to another account",
        )

    secret = (body.webhook_secret or "").strip() or None
    await db.execute(
        update(Clients)
        .where(Clients.id == client.id)
        .values(aggregator_location_id=location_id, aggregator_webhook_secret=secret)
    )
    await db.commit()
    logger.info("Aggregator location %s connected to client %s", location_id, client.id)
    return AggregatorConnectionResponse(
        connected=True, location_id=location_id, webhook_secret_set=bool(secret)
    )


@router.get("/connection", response_model=AggregatorConnectionResponse)
async def get_aggregator_connection(
    client: Clients = Depends(get_restaurant_client),
    db: AsyncSession = Depends(get_db),
):
    """Read the caller's aggregator-middleware connection status."""
    location_id = (client.aggregator_location_id or "").strip() or None
    return AggregatorConnectionResponse(
        connected=bool(location_id),
        location_id=location_id,
        webhook_secret_set=bool(client.aggregator_webhook_secret),
    )


# ---------- Webhook ingest (F-060) ----------
@router.post("/{provider}/webhook")
async def aggregator_webhook(
    provider: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_webhook_signature: Optional[str] = Header(default=None, alias="X-Webhook-Signature"),
):
    """Ingest a Deliverect-class order webhook (unauthenticated — middleware caller).

    Routes the order to the owning client by location id, verifies the HMAC
    signature when the client configured a secret, enforces the restaurant gates,
    then materializes the order as a fired KDS ticket + a ZATCA sale. Always returns
    200 (with a status) for a parseable, known-location request so the middleware
    does not retry indefinitely; only a bad signature returns 401.
    """
    provider = (provider or "").strip().lower()
    if provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail=f"Unknown aggregator provider '{provider}'")

    raw_body = await request.body()
    try:
        payload = json.loads(raw_body or b"{}")
        if not isinstance(payload, dict):
            raise ValueError("payload is not an object")
    except (ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    location_id = extract_location(payload)
    if not location_id:
        return {"status": "ignored", "reason": "missing_location"}

    client = (
        await db.execute(
            select(Clients).where(Clients.aggregator_location_id == location_id)
        )
    ).scalar_one_or_none()
    if client is None:
        logger.info("Aggregator webhook for unknown location %s — ignored", location_id)
        return {"status": "ignored", "reason": "unknown_location"}

    # Verify the signature BEFORE doing any work (F-060 security).
    if not verify_aggregator_signature(
        client.aggregator_webhook_secret, raw_body, x_webhook_signature
    ):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # Restaurant gates: aggregator ingest is a restaurant-vertical feature.
    if (client.business_type or "retail") not in RESTAURANT_BUSINESS_TYPES:
        return {"status": "ignored", "reason": "not_a_restaurant"}
    if not await is_feature_enabled(db, client.id, "restaurant"):
        logger.info("restaurant disabled for client %s — aggregator order ignored", client.id)
        return {"status": "feature_disabled"}

    vat_rate = await get_effective_tax_rate(db, 15.0)
    result = await ingest_aggregator_order(db, client, payload, provider, vat_rate)
    return result
