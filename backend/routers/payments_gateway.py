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
from models.terminals import Terminals
from schemas.auth import UserResponse
from services.payment_gateway import (
    CARD_LIKE_TENDERS,
    SUPPORTED_TENDER_TYPES,
    TERMINAL_PROVIDERS,
    GatewayNotConfigured,
    PaymentDeclined,
    get_gateway,
    get_terminal_gateway,
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


# ---------------------------------------------------------------------------
# Integrated in-store terminals (HW-03 / PAY-05, F-005)
# ---------------------------------------------------------------------------
class TerminalRegisterRequest(BaseModel):
    provider: Optional[str] = "geidea"
    label: Optional[str] = None
    serial: Optional[str] = None
    branch_id: Optional[int] = None


class TerminalResponse(BaseModel):
    id: int
    provider: str
    label: Optional[str] = None
    serial: Optional[str] = None
    branch_id: Optional[int] = None
    status: str

    class Config:
        from_attributes = True


class TerminalChargeRequest(BaseModel):
    terminal_id: int
    amount: float
    tender_type: Optional[str] = "mada"
    currency: Optional[str] = "SAR"
    # Sandbox-only outcome hint ("approve"/"decline"); a live terminal ignores it.
    simulate: Optional[str] = None


@router.post("/terminals", response_model=TerminalResponse, status_code=201)
async def register_terminal(
    data: TerminalRegisterRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Register an in-store SoftPOS terminal the merchant has paired (HW-03).

    The terminal is owner-scoped; a card-like tender can later be pushed to it via
    ``POST /payments/terminal/charge``. Only wired providers are accepted.
    """
    client = await _client_for_user(db, str(current_user.id))
    provider = (data.provider or "geidea").strip().lower()
    if provider not in TERMINAL_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported terminal provider '{provider}'. Allowed: {', '.join(TERMINAL_PROVIDERS)}",
        )
    terminal = Terminals(
        user_id=str(current_user.id),
        client_id=client.id,
        branch_id=data.branch_id,
        provider=provider,
        label=data.label,
        serial=data.serial,
        status="active",
    )
    db.add(terminal)
    await db.commit()
    await db.refresh(terminal)
    logger.debug("Registered %s terminal %s for client %s", provider, terminal.id, client.id)
    return terminal


@router.get("/terminals", response_model=list[TerminalResponse])
async def list_terminals(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List the caller's registered terminals (owner-scoped, SEC-02)."""
    await _client_for_user(db, str(current_user.id))
    rows = (
        await db.execute(
            select(Terminals).where(Terminals.user_id == str(current_user.id))
        )
    ).scalars().all()
    return rows


@router.post("/terminal/charge", response_model=ChargeResponse)
async def charge_terminal(
    data: TerminalChargeRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Push an amount to a paired SoftPOS terminal and capture the approval (HW-03).

    The IB §4.6 ``POST /payments/terminal/charge {terminal_id, amount}`` flow: the
    amount is pushed to the named terminal, the customer taps, and a real approval
    (network + approval code + RRN) is captured as an ``authorized`` tender the
    subsequent sale references — or a **decline returns 402 and nothing persists**
    (so a terminal decline blocks the sale, PAY-05). Routed through the Geidea
    SoftPOS adapter (live once ``GEIDEA_API_KEY`` + a paired device exist, else the
    hardware-free sandbox). The terminal must belong to the caller (SEC-02).
    """
    client = await _client_for_user(db, str(current_user.id))
    terminal = (
        await db.execute(
            select(Terminals).where(
                Terminals.id == data.terminal_id,
                Terminals.user_id == str(current_user.id),
            )
        )
    ).scalar_one_or_none()
    if terminal is None:
        raise HTTPException(status_code=404, detail="Terminal not found")
    if (terminal.status or "active") != "active":
        raise HTTPException(status_code=400, detail="Terminal is not active")

    ttype = normalize_tender_type(data.tender_type)
    amount = round(float(data.amount or 0), 2)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be greater than 0")
    if not requires_capture(ttype):
        raise HTTPException(
            status_code=400,
            detail=f"Tender '{ttype}' settles internally and is not charged via a terminal",
        )

    gateway = get_terminal_gateway(terminal.provider)
    try:
        result = await gateway.charge(
            amount,
            ttype,
            currency=data.currency or "SAR",
            simulate=data.simulate,
            metadata={"terminal_serial": terminal.serial},
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
