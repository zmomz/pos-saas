"""Gift card / store-credit service (CRM-03 / PRC-05, F-038).

Issue a prepaid card, look it up by its bearer code within the owner's scope,
validate it for a redemption amount, and **atomically decrement** its balance as a
sale tender. Redemption mirrors the discount ``consume`` pattern: a single
conditional UPDATE that only succeeds while the card is active, unexpired, and has
enough balance — so concurrent redemptions cannot overdraw a card (the cap is
enforced in SQL, not by a read-then-write race) and a rolled-back sale never spends
it (no commit happens here; it runs inside the sale's transaction).
"""
import logging
import secrets
from datetime import datetime
from typing import Optional

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.gift_cards import Gift_cards

logger = logging.getLogger(__name__)

# Status values the card can hold.
ACTIVE = "active"
REDEEMED = "redeemed"
EXPIRED = "expired"
VOID = "void"

# Below this the balance is treated as fully exhausted (float-noise tolerance).
_ZERO_EPSILON = 0.0001


class GiftCardError(ValueError):
    """A gift card failed server-side validation (mapped to HTTP 400).

    Raised when a code is unknown/foreign, the card is inactive/void/expired, or
    its balance is below the requested redemption amount. PRC-05 requires the
    server — not the client — to make this judgement.
    """


def generate_gift_card_code() -> str:
    """A CSPRNG bearer code, e.g. ``GC-7F3A9C2D1B4E``. Unguessable by design."""
    return "GC-" + secrets.token_hex(6).upper()


def is_expired(card: Gift_cards, now: Optional[datetime] = None) -> bool:
    """True when the card has a past ``expiry_date``."""
    if not card.expiry_date:
        return False
    return card.expiry_date < (now or datetime.now())


class GiftCardsService:
    """Service layer for gift card issue / lookup / redemption."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def issue(
        self,
        *,
        user_id: str,
        client_id: int,
        amount: float,
        currency: str = "SAR",
        expiry_date: Optional[datetime] = None,
        customer_id: Optional[int] = None,
        code: Optional[str] = None,
    ) -> Gift_cards:
        """Issue (and persist) a new active gift card with ``amount`` balance."""
        face_value = round(float(amount or 0), 2)
        card = Gift_cards(
            user_id=str(user_id),
            client_id=client_id,
            code=(code or generate_gift_card_code()),
            currency=currency or "SAR",
            initial_balance=face_value,
            balance=face_value,
            status=ACTIVE,
            expiry_date=expiry_date,
            customer_id=customer_id,
        )
        self.db.add(card)
        await self.db.commit()
        await self.db.refresh(card)
        logger.info("Issued gift card %s (balance %.2f) for client %s", card.id, face_value, client_id)
        return card

    async def get_by_code(self, code: str, user_id: str) -> Optional[Gift_cards]:
        """Look up a card by its code within the owner's scope (case-insensitive)."""
        result = await self.db.execute(
            select(Gift_cards).where(
                func.lower(Gift_cards.code) == (code or "").strip().lower(),
                Gift_cards.user_id == str(user_id),
            )
        )
        return result.scalars().first()

    async def list_for_user(self, user_id: str) -> list[Gift_cards]:
        """All cards owned by ``user_id``, newest first (owner-scoped, SEC-02)."""
        result = await self.db.execute(
            select(Gift_cards)
            .where(Gift_cards.user_id == str(user_id))
            .order_by(Gift_cards.id.desc())
        )
        return list(result.scalars().all())

    async def validate(
        self, code: str, amount: float, user_id: str, now: Optional[datetime] = None
    ) -> Gift_cards:
        """Validate a card for a redemption ``amount`` (PRC-05). Read-only.

        Enforces, server-side: the code exists in the caller's scope, is active
        (not void/redeemed), is not expired, and has at least ``amount`` balance.
        Raises ``GiftCardError`` (→ HTTP 400) otherwise. Does **not** decrement —
        call ``redeem`` for that, atomically with the sale.
        """
        card = await self.get_by_code(code, user_id)
        if not card:
            raise GiftCardError("Invalid gift card code")
        if (card.status or ACTIVE) == VOID:
            raise GiftCardError("This gift card has been cancelled")
        if is_expired(card, now):
            raise GiftCardError("This gift card has expired")
        if (card.status or ACTIVE) != ACTIVE or (card.balance or 0) <= _ZERO_EPSILON:
            raise GiftCardError("This gift card has no remaining balance")
        if round(float(amount or 0), 2) > round(float(card.balance or 0), 2) + _ZERO_EPSILON:
            raise GiftCardError(
                f"Gift card balance {float(card.balance or 0):.2f} is less than {float(amount):.2f}"
            )
        return card

    async def redeem(
        self, card_id: int, amount: float, user_id: str, now: Optional[datetime] = None
    ) -> bool:
        """Atomically decrement ``balance`` by ``amount`` enforcing all guards. No commit.

        A single conditional UPDATE decrements only while the card is active, not
        expired, and still has enough balance — so concurrent redemptions cannot
        overdraw it (the guard is in SQL, not a read-then-write race). Runs inside
        the caller's transaction (the sale), so the decrement commits with the sale
        and rolls back if the sale fails. Returns ``True`` when the redemption
        succeeded, ``False`` when the guard rejected it (race-lost / exhausted).

        When the redemption brings the balance to zero the status is flipped to
        ``redeemed`` in the same transaction.
        """
        now = now or datetime.now()
        amount = round(float(amount or 0), 2)
        result = await self.db.execute(
            update(Gift_cards)
            .where(
                Gift_cards.id == card_id,
                Gift_cards.user_id == str(user_id),
                Gift_cards.status == ACTIVE,
                func.coalesce(Gift_cards.balance, 0) >= amount,
                or_(Gift_cards.expiry_date.is_(None), Gift_cards.expiry_date >= now),
            )
            .values(balance=func.coalesce(Gift_cards.balance, 0) - amount)
        )
        if (result.rowcount or 0) <= 0:
            return False
        # Exhausted cards become ``redeemed`` so they're filtered from future use.
        await self.db.execute(
            update(Gift_cards)
            .where(
                Gift_cards.id == card_id,
                Gift_cards.user_id == str(user_id),
                func.coalesce(Gift_cards.balance, 0) <= _ZERO_EPSILON,
            )
            .values(status=REDEEMED)
        )
        return True
