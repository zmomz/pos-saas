"""Gift card / store-credit surface (CRM-03 / PRC-05, F-038).

The merchant issues prepaid store credit, lists their issued cards, and looks up a
card's balance. Redemption itself happens on the **atomic sale path**
(`routers/pos.py`) as a ``giftcard`` tender — this router is the management +
balance-lookup surface, not the redemption path.

Owner-scoped (SEC-02): a client tenancy is required and every read/write filters on
the caller's ``user_id`` so one client can neither see nor look up another client's
cards.
"""
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.tenancy import get_owner_id
from models.clients import Clients
from models.gift_cards import Gift_cards
from services.gift_cards import (
    ACTIVE,
    GiftCardError,
    GiftCardsService,
    is_expired,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/gift-cards", tags=["gift-cards"])


async def _client_for_user(db: AsyncSession, user_id: str) -> Clients:
    result = await db.execute(select(Clients).where(Clients.user_id == user_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=403, detail="Only clients can manage gift cards")
    return client


def _naive(dt: Optional[datetime]) -> Optional[datetime]:
    """Drop tzinfo so comparisons against the (naive) DB timestamps are consistent."""
    if dt is not None and dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


class IssueGiftCardRequest(BaseModel):
    amount: float
    currency: Optional[str] = "SAR"
    expiry_date: Optional[datetime] = None
    customer_id: Optional[int] = None


class GiftCardResponse(BaseModel):
    id: int
    code: str
    currency: str
    initial_balance: float
    balance: float
    status: str
    expiry_date: Optional[datetime] = None
    customer_id: Optional[int] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class GiftCardListResponse(BaseModel):
    """A server-side-paginated page of gift cards plus the full ``total`` (OPS-05)."""

    items: List[GiftCardResponse]
    total: int


class GiftCardBalanceResponse(BaseModel):
    code: str
    balance: float
    status: str
    expiry_date: Optional[datetime] = None
    is_redeemable: bool


class ReloadGiftCardRequest(BaseModel):
    amount: float


class RefundToGiftCardRequest(BaseModel):
    amount: float
    transaction_id: Optional[int] = None


class GiftCardLedgerEntryResponse(BaseModel):
    id: int
    entry_type: str
    amount: float
    balance_after: float
    transaction_id: Optional[int] = None
    note: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


def _to_response(card: Gift_cards) -> GiftCardResponse:
    return GiftCardResponse(
        id=card.id,
        code=card.code,
        currency=card.currency or "SAR",
        initial_balance=card.initial_balance or 0,
        balance=card.balance or 0,
        status=card.status or ACTIVE,
        expiry_date=card.expiry_date,
        customer_id=card.customer_id,
        created_at=card.created_at,
    )


@router.post("", response_model=GiftCardResponse, status_code=201)
async def issue_gift_card(
    data: IssueGiftCardRequest,
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Issue a new active gift card (prepaid store credit) with a CSPRNG code.

    The amount is the card's face value; the server generates the bearer code (never
    trusted from the client). Owner-scoped to the caller's client.
    """
    client = await _client_for_user(db, owner_id)
    amount = round(float(data.amount or 0), 2)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be greater than 0")
    service = GiftCardsService(db)
    card = await service.issue(
        user_id=owner_id,
        client_id=client.id,
        amount=amount,
        currency=data.currency or "SAR",
        expiry_date=_naive(data.expiry_date),
        customer_id=data.customer_id,
    )
    return _to_response(card)


@router.get("", response_model=GiftCardListResponse)
async def list_gift_cards(
    skip: int = Query(0, ge=0, description="Rows to skip (pagination offset)"),
    limit: int = Query(50, ge=1, le=200, description="Max cards to return"),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """List the caller's issued gift cards, newest first (owner-scoped, SEC-02).

    Server-side paginated (OPS-05): ``skip``/``limit`` bound the query so a client
    with thousands of cards never load-everythings; ``total`` is the full count so
    the UI can page.
    """
    await _client_for_user(db, owner_id)
    service = GiftCardsService(db)
    cards = await service.list_for_user(owner_id, skip=skip, limit=limit)
    total = await service.count_for_user(owner_id)
    return GiftCardListResponse(items=[_to_response(c) for c in cards], total=total)


@router.get("/{code}/balance", response_model=GiftCardBalanceResponse)
async def gift_card_balance(
    code: str,
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Look up a card's balance + redeemability within the owner's scope (SEC-02).

    A foreign/unknown code is a 404 so one client cannot probe another's cards.
    """
    await _client_for_user(db, owner_id)
    service = GiftCardsService(db)
    card = await service.get_by_code(code, owner_id)
    if not card:
        raise HTTPException(status_code=404, detail="Gift card not found")
    redeemable = (
        (card.status or ACTIVE) == ACTIVE
        and not is_expired(card)
        and (card.balance or 0) > 0
    )
    return GiftCardBalanceResponse(
        code=card.code,
        balance=card.balance or 0,
        status=card.status or ACTIVE,
        expiry_date=card.expiry_date,
        is_redeemable=redeemable,
    )


@router.post("/{card_id}/void", response_model=GiftCardResponse)
async def void_gift_card(
    card_id: int,
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Cancel a gift card — freeze its balance and make it unredeemable (SEC-02).

    The balance is preserved (frozen, not zeroed) for the audit trail; the card can
    no longer be redeemed. Foreign/unknown ids are a 404 so one client cannot void
    another's card.
    """
    await _client_for_user(db, owner_id)
    service = GiftCardsService(db)
    try:
        card = await service.void(card_id, owner_id)
    except GiftCardError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not card:
        raise HTTPException(status_code=404, detail="Gift card not found")
    return _to_response(card)


@router.post("/{card_id}/reload", response_model=GiftCardResponse)
async def reload_gift_card(
    card_id: int,
    data: ReloadGiftCardRequest,
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Top up a card's balance (owner-scoped). Reactivates a previously exhausted card."""
    await _client_for_user(db, owner_id)
    service = GiftCardsService(db)
    try:
        card = await service.reload(card_id, data.amount, owner_id)
    except GiftCardError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not card:
        raise HTTPException(status_code=404, detail="Gift card not found")
    return _to_response(card)


@router.post("/{card_id}/refund", response_model=GiftCardResponse)
async def refund_to_gift_card(
    card_id: int,
    data: RefundToGiftCardRequest,
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Refund a sale's value back onto a gift card (owner-scoped), recorded as a refund."""
    await _client_for_user(db, owner_id)
    service = GiftCardsService(db)
    try:
        card = await service.refund_to_card(
            card_id, data.amount, owner_id, transaction_id=data.transaction_id
        )
    except GiftCardError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not card:
        raise HTTPException(status_code=404, detail="Gift card not found")
    return _to_response(card)


@router.get("/{card_id}/ledger", response_model=List[GiftCardLedgerEntryResponse])
async def gift_card_ledger(
    card_id: int,
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """The card's management-movement audit rows (void/reload/refund), oldest first."""
    await _client_for_user(db, owner_id)
    service = GiftCardsService(db)
    card = await service.get_by_id(card_id, owner_id)
    if not card:
        raise HTTPException(status_code=404, detail="Gift card not found")
    entries = await service.list_ledger(card_id, owner_id)
    return [GiftCardLedgerEntryResponse.model_validate(e) for e in entries]
