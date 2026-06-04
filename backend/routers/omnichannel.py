"""Omnichannel router — Salla connector (OMN-01..03, F-046).

Mounts at ``/api/v1/omnichannel``. The first connector of the "sell online too"
vision (INTENDED_BEHAVIOR §4.12): a merchant connects their Salla store, Salla pushes
order webhooks here, and each online order is materialized as a real POS sale that
appears in the back-office and decrements the **same shared stock** (OMN-03).

Surfaces:
- ``POST /salla/connect``        — client registers their Salla store id (+ optional
  webhook secret). Owner-scoped, gated by the per-client ``omnichannel`` feature.
- ``GET  /salla/connection``     — read the current connection status.
- ``POST /salla/webhook``        — **unauthenticated** (Salla is the caller). Routed
  to the owning client by store id, signature-verified when a secret is set, then
  ingested. Acks 200 even when ignored so Salla does not retry forever.
- ``GET  /channel-orders``       — owner-scoped list of imported online orders for
  the back-office.
"""
import json
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Header
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.auth import get_current_user
from dependencies.features import is_feature_enabled, require_feature
from models.channel_orders import Channel_orders
from models.clients import Clients
from schemas.auth import UserResponse
from services.omnichannel import ingest_salla_order, verify_salla_signature

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/omnichannel", tags=["omnichannel"])


# ---------- Schemas ----------
class SallaConnectRequest(BaseModel):
    store_id: str
    webhook_secret: Optional[str] = None


class SallaConnectionResponse(BaseModel):
    connected: bool
    store_id: Optional[str] = None
    webhook_secret_set: bool = False


class ChannelOrderResponse(BaseModel):
    id: int
    provider: str
    external_order_id: str
    external_reference: Optional[str] = None
    transaction_id: Optional[int] = None
    status: str
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    total_amount: Optional[float] = None
    currency: Optional[str] = None
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


class ChannelOrderListResponse(BaseModel):
    items: List[ChannelOrderResponse]
    total: int
    page: int
    page_size: int


# ---------- Helper: resolve the caller's client ----------
async def _client_for_user(db: AsyncSession, user_id: str) -> Clients:
    client = (
        await db.execute(select(Clients).where(Clients.user_id == str(user_id)))
    ).scalar_one_or_none()
    if client is None:
        raise HTTPException(status_code=403, detail="Only client merchants can use omnichannel features")
    return client


# ---------- Connect a Salla store (OMN-01) ----------
@router.post(
    "/salla/connect",
    response_model=SallaConnectionResponse,
    dependencies=[Depends(require_feature("omnichannel"))],
)
async def connect_salla(
    body: SallaConnectRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Register (or update) the caller's Salla store connection.

    The ``store_id`` routes incoming webhooks to this client, so it must be unique
    across merchants — a value already claimed by another client is rejected 409.
    """
    store_id = (body.store_id or "").strip()
    if not store_id:
        raise HTTPException(status_code=400, detail="store_id is required")

    client = await _client_for_user(db, str(current_user.id))

    # Uniqueness across tenants — two clients cannot share a Salla store id.
    clash = (
        await db.execute(
            select(Clients.id).where(
                Clients.salla_store_id == store_id,
                Clients.id != client.id,
            )
        )
    ).scalar_one_or_none()
    if clash is not None:
        raise HTTPException(status_code=409, detail="This Salla store is already connected to another account")

    secret = (body.webhook_secret or "").strip() or None
    await db.execute(
        update(Clients)
        .where(Clients.id == client.id)
        .values(salla_store_id=store_id, salla_webhook_secret=secret)
    )
    await db.commit()
    logger.info("Salla store %s connected to client %s", store_id, client.id)
    return SallaConnectionResponse(connected=True, store_id=store_id, webhook_secret_set=bool(secret))


@router.get("/salla/connection", response_model=SallaConnectionResponse)
async def get_salla_connection(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Read the caller's Salla connection status."""
    client = await _client_for_user(db, str(current_user.id))
    store_id = (client.salla_store_id or "").strip() or None
    return SallaConnectionResponse(
        connected=bool(store_id),
        store_id=store_id,
        webhook_secret_set=bool(client.salla_webhook_secret),
    )


# ---------- Salla webhook ingest (OMN-03) ----------
@router.post("/salla/webhook")
async def salla_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_salla_signature: Optional[str] = Header(default=None, alias="X-Salla-Signature"),
):
    """Ingest a Salla order webhook (unauthenticated — Salla is the caller).

    Routes the order to the owning client by ``merchant``→``salla_store_id``,
    verifies the HMAC signature when the client configured a secret, checks the
    ``omnichannel`` feature is enabled, then materializes the order as a POS sale.
    Always returns 200 (with a status) for a parseable request so Salla does not
    retry indefinitely; only a bad signature returns 401.
    """
    raw_body = await request.body()
    try:
        payload = json.loads(raw_body or b"{}")
        if not isinstance(payload, dict):
            raise ValueError("payload is not an object")
    except (ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    merchant = payload.get("merchant")
    if merchant is None and isinstance(payload.get("data"), dict):
        merchant = payload["data"].get("merchant") or payload["data"].get("store_id")
    store_id = str(merchant).strip() if merchant is not None else ""
    if not store_id:
        return {"status": "ignored", "reason": "missing_merchant"}

    client = (
        await db.execute(select(Clients).where(Clients.salla_store_id == store_id))
    ).scalar_one_or_none()
    if client is None:
        # Unknown store — ack so Salla stops retrying; nothing to do.
        logger.info("Salla webhook for unknown store %s — ignored", store_id)
        return {"status": "ignored", "reason": "unknown_store"}

    if not verify_salla_signature(client.salla_webhook_secret, raw_body, x_salla_signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    if not await is_feature_enabled(db, client.id, "omnichannel"):
        logger.info("omnichannel disabled for client %s — Salla order ignored", client.id)
        return {"status": "feature_disabled"}

    # Only import order-creation events; other events (refund/status) are out of
    # scope for this first slice.
    event = (payload.get("event") or "").strip().lower()
    if event and "order" not in event:
        return {"status": "ignored", "reason": f"unhandled_event:{event}"}

    result = await ingest_salla_order(db, client, payload)
    return result


# ---------- Back-office: list imported online orders (OMN-03) ----------
@router.get("/channel-orders", response_model=ChannelOrderListResponse)
async def list_channel_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List the caller's imported online orders, newest first (owner-scoped)."""
    client = await _client_for_user(db, str(current_user.id))
    offset = (page - 1) * page_size

    base = select(Channel_orders).where(Channel_orders.client_id == client.id)
    total = (
        await db.execute(
            select(func.count(Channel_orders.id)).where(Channel_orders.client_id == client.id)
        )
    ).scalar() or 0

    rows = (
        await db.execute(
            base.order_by(Channel_orders.created_at.desc()).offset(offset).limit(page_size)
        )
    ).scalars().all()

    items = [
        ChannelOrderResponse(
            id=r.id,
            provider=r.provider,
            external_order_id=r.external_order_id,
            external_reference=r.external_reference,
            transaction_id=r.transaction_id,
            status=r.status,
            customer_name=r.customer_name,
            customer_phone=r.customer_phone,
            total_amount=r.total_amount,
            currency=r.currency,
            created_at=r.created_at.isoformat() if r.created_at else None,
        )
        for r in rows
    ]
    return ChannelOrderListResponse(items=items, total=total, page=page, page_size=page_size)
