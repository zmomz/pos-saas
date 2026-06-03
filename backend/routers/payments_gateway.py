"""Standalone payment-capture surface (PAY-05/06, F-002).

The atomic sale (`routers/pos.py`) captures card-like tenders inline, which is the
authoritative path. This router exposes the *capture* as a first-class surface so:

* a cashier can pre-authorize a card/Mada tender on a connected terminal before
  ringing the sale (the IB §4.6 `POST /payments/terminal/charge` flow), and
* the supported Saudi tender taxonomy is queryable to drive the POS picker.

Both run through the same :mod:`services.payment_gateway` abstraction (sandbox by
default, Moyasar once configured), so no PAN ever reaches the server (PAY-09).
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.auth import get_current_user
from models.clients import Clients
from models.payment_tenders import PaymentTenders
from schemas.auth import UserResponse
from services.payment_gateway import (
    CARD_LIKE_TENDERS,
    SUPPORTED_TENDER_TYPES,
    GatewayNotConfigured,
    PaymentDeclined,
    get_gateway,
    normalize_tender_type,
    requires_capture,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/payments", tags=["payments"])


async def _client_for_user(db: AsyncSession, user_id: str) -> Clients:
    result = await db.execute(select(Clients).where(Clients.user_id == user_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=403, detail="Only clients can capture payments")
    return client


class ChargeRequest(BaseModel):
    tender_type: str
    amount: float
    currency: Optional[str] = "SAR"
    # Gateway-side card token from client tokenization (no PAN on the server).
    token: Optional[str] = None
    # Sandbox-only outcome hint ("approve"/"decline"); real gateways ignore it.
    simulate: Optional[str] = None


class ChargeResponse(BaseModel):
    approved: bool
    tender_id: Optional[int] = None
    tender_type: str
    amount: float
    network: Optional[str] = None
    approval_code: Optional[str] = None
    rrn: Optional[str] = None
    gateway_ref: Optional[str] = None
    last4: Optional[str] = None
    gateway: str
    status: str


@router.get("/tender-types")
async def list_tender_types(
    current_user: UserResponse = Depends(get_current_user),
):
    """The tender taxonomy the POS understands (drives the payment picker).

    ``card_like`` tenders require a real gateway approval at sale time; the rest
    settle internally.
    """
    return {
        "tender_types": list(SUPPORTED_TENDER_TYPES),
        "card_like": sorted(CARD_LIKE_TENDERS),
        "gateway": get_gateway().name,
    }


@router.post("/charge", response_model=ChargeResponse)
async def charge_tender(
    data: ChargeRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Capture a single tender via the active gateway (terminal/online pre-auth).

    A card-like tender obtains a real approval; a decline returns **402** and
    nothing is persisted. An approved capture is recorded as an ``authorized``
    tender (not yet linked to a sale) which the subsequent sale references. Cash
    and internal tenders are not chargeable here (use the sale path).
    """
    client = await _client_for_user(db, str(current_user.id))
    ttype = normalize_tender_type(data.tender_type)
    amount = round(float(data.amount or 0), 2)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be greater than 0")
    if not requires_capture(ttype):
        raise HTTPException(
            status_code=400,
            detail=f"Tender '{ttype}' settles internally and is not charged via the gateway",
        )

    gateway = get_gateway()
    try:
        result = await gateway.charge(
            amount, ttype, currency=data.currency or "SAR", token=data.token, simulate=data.simulate
        )
    except GatewayNotConfigured as exc:
        raise HTTPException(status_code=402, detail=f"Payment not captured: {exc}")
    except PaymentDeclined as exc:
        raise HTTPException(status_code=402, detail=f"Payment declined: {exc.reason}")
    if not result.approved:
        raise HTTPException(
            status_code=402,
            detail=f"Payment declined: {result.decline_reason or 'declined'}",
        )

    tender = PaymentTenders(
        user_id=str(current_user.id),
        client_id=client.id,
        transaction_id=None,
        tender_type=ttype,
        amount=amount,
        network=result.network,
        approval_code=result.approval_code,
        rrn=result.rrn,
        gateway_ref=result.gateway_ref,
        last4=result.last4,
        token=result.token,
        gateway=result.gateway,
        status="authorized",
    )
    db.add(tender)
    await db.commit()
    await db.refresh(tender)

    return ChargeResponse(
        approved=True,
        tender_id=tender.id,
        tender_type=ttype,
        amount=amount,
        network=result.network,
        approval_code=result.approval_code,
        rrn=result.rrn,
        gateway_ref=result.gateway_ref,
        last4=result.last4,
        gateway=result.gateway,
        status=tender.status,
    )
