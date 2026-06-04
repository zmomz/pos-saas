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

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.auth import get_current_user
from models.clients import Clients
from models.gift_cards import Gift_cards
from schemas.auth import UserResponse
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


class GiftCardBalanceResponse(BaseModel):
    code: str
    balance: float
    status: str
    expiry_date: Optional[datetime] = None
    is_redeemable: bool


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
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Issue a new active gift card (prepaid store credit) with a CSPRNG code.

    The amount is the card's face value; the server generates the bearer code (never
    trusted from the client). Owner-scoped to the caller's client.
    """
    client = await _client_for_user(db, str(current_user.id))
    amount = round(float(data.amount or 0), 2)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be greater than 0")
    service = GiftCardsService(db)
    card = await service.issue(
        user_id=str(current_user.id),
        client_id=client.id,
        amount=amount,
        currency=data.currency or "SAR",
        expiry_date=_naive(data.expiry_date),
        customer_id=data.customer_id,
    )
    return _to_response(card)


@router.get("", response_model=List[GiftCardResponse])
async def list_gift_cards(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List the caller's issued gift cards, newest first (owner-scoped, SEC-02)."""
    await _client_for_user(db, str(current_user.id))
    service = GiftCardsService(db)
    cards = await service.list_for_user(str(current_user.id))
    return [_to_response(c) for c in cards]


@router.get("/{code}/balance", response_model=GiftCardBalanceResponse)
async def gift_card_balance(
    code: str,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Look up a card's balance + redeemability within the owner's scope (SEC-02).

    A foreign/unknown code is a 404 so one client cannot probe another's cards.
    """
    await _client_for_user(db, str(current_user.id))
    service = GiftCardsService(db)
    card = await service.get_by_code(code, str(current_user.id))
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
