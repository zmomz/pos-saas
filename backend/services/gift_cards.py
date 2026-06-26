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

from core.money import quantize_money
from models.gift_card_ledger import GiftCardLedger
from models.gift_cards import Gift_cards

logger = logging.getLogger(__name__)

# Status values the card can hold.
ACTIVE = "active"
REDEEMED = "redeemed"
EXPIRED = "expired"
VOID = "void"


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
        face_value = quantize_money(amount or 0)
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

    async def get_by_id(self, card_id: int, user_id: str) -> Optional[Gift_cards]:
        """Look up a card by id within the owner's scope (SEC-02)."""
        result = await self.db.execute(
            select(Gift_cards).where(
                Gift_cards.id == card_id,
                Gift_cards.user_id == str(user_id),
            )
        )
        return result.scalars().first()

    async def get_by_code(self, code: str, user_id: str) -> Optional[Gift_cards]:
        """Look up a card by its code within the owner's scope (case-insensitive)."""
        result = await self.db.execute(
            select(Gift_cards).where(
                func.lower(Gift_cards.code) == (code or "").strip().lower(),
                Gift_cards.user_id == str(user_id),
            )
        )
        return result.scalars().first()

    async def list_for_user(
        self, user_id: str, *, skip: int = 0, limit: Optional[int] = None
    ) -> list[Gift_cards]:
        """A page of cards owned by ``user_id``, newest first (owner-scoped, SEC-02).

        Server-side paginated (OPS-05): ``limit`` bounds the rows materialized so a
        client with thousands of issued cards never load-everythings. ``limit=None``
        returns the full set (used by internal callers that already constrain scope).
        """
        stmt = (
            select(Gift_cards)
            .where(Gift_cards.user_id == str(user_id))
            .order_by(Gift_cards.id.desc())
            .offset(skip)
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count_for_user(self, user_id: str) -> int:
        """Total cards owned by ``user_id`` (for the paginated list's ``total``)."""
        result = await self.db.execute(
            select(func.count(Gift_cards.id)).where(Gift_cards.user_id == str(user_id))
        )
        return int(result.scalar() or 0)

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
        balance = quantize_money(card.balance or 0)
        if (card.status or ACTIVE) != ACTIVE or balance <= 0:
            raise GiftCardError("This gift card has no remaining balance")
        if quantize_money(amount or 0) > balance:
            raise GiftCardError(
                f"Gift card balance {balance:.2f} is less than {quantize_money(amount or 0):.2f}"
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
        amount = quantize_money(amount or 0)
        result = await self.db.execute(
            update(Gift_cards)
            .where(
                Gift_cards.id == card_id,
                Gift_cards.user_id == str(user_id),
                Gift_cards.status == ACTIVE,
                func.coalesce(Gift_cards.balance, 0) >= amount,
                or_(Gift_cards.expiry_date.is_(None), Gift_cards.expiry_date >= now),
            )
            # FIN-03: round the SQL decrement to 2dp so the stored balance never
            # carries float subtraction drift (0.30 - 0.10 -> 0.20, not 0.19999…)
            # that the next redemption's ``>= amount`` guard would wrongly reject.
            .values(balance=func.round(func.coalesce(Gift_cards.balance, 0) - amount, 2))
        )
        if (result.rowcount or 0) <= 0:
            return False
        # Exhausted cards become ``redeemed`` so they're filtered from future use.
        await self.db.execute(
            update(Gift_cards)
            .where(
                Gift_cards.id == card_id,
                Gift_cards.user_id == str(user_id),
                func.coalesce(Gift_cards.balance, 0) <= 0,
            )
            .values(status=REDEEMED)
        )
        return True

    # ------------------------------------------------------------------
    # Management movements (ISSUE-057): void / reload / refund-to-card.
    # Each commits and writes a ``gift_card_ledger`` audit row recording the
    # change and the resulting balance. Redemptions are NOT recorded here —
    # they live as ``giftcard`` tenders on the sale.
    # ------------------------------------------------------------------
    def _record(
        self,
        card: Gift_cards,
        entry_type: str,
        amount: float,
        balance_after: float,
        transaction_id: Optional[int] = None,
        note: Optional[str] = None,
    ) -> None:
        self.db.add(
            GiftCardLedger(
                user_id=card.user_id,
                client_id=card.client_id,
                gift_card_id=card.id,
                entry_type=entry_type,
                amount=quantize_money(amount or 0),
                balance_after=quantize_money(balance_after or 0),
                transaction_id=transaction_id,
                note=note,
            )
        )

    async def void(self, card_id: int, user_id: str) -> Optional[Gift_cards]:
        """Cancel a card: freeze its balance and flip status to ``void``.

        The balance is left intact (frozen, not zeroed) so the audit trail keeps
        what was on the card; the ``void`` status makes it unredeemable (the sale
        path's ``validate`` already rejects a void card). Records a ledger entry.
        Returns ``None`` when the card isn't in the caller's scope (→ 404).
        """
        card = await self.get_by_id(card_id, user_id)
        if not card:
            return None
        if (card.status or ACTIVE) == VOID:
            raise GiftCardError("This gift card is already cancelled")
        card.status = VOID
        self._record(card, VOID, 0.0, card.balance or 0)
        await self.db.commit()
        await self.db.refresh(card)
        logger.info("Voided gift card %s (frozen balance %.2f)", card.id, card.balance or 0)
        return card

    async def reload(
        self, card_id: int, amount: float, user_id: str
    ) -> Optional[Gift_cards]:
        """Top up a card's balance by ``amount`` (records a ``reload`` ledger entry)."""
        return await self._credit(card_id, amount, user_id, "reload")

    async def refund_to_card(
        self,
        card_id: int,
        amount: float,
        user_id: str,
        transaction_id: Optional[int] = None,
    ) -> Optional[Gift_cards]:
        """Refund ``amount`` back onto a card (records a ``refund`` ledger entry).

        Optionally links the refunded sale via ``transaction_id``.
        """
        return await self._credit(card_id, amount, user_id, "refund", transaction_id)

    async def _credit(
        self,
        card_id: int,
        amount: float,
        user_id: str,
        entry_type: str,
        transaction_id: Optional[int] = None,
    ) -> Optional[Gift_cards]:
        """Increase a card's balance and record it. Shared by reload + refund.

        Rejects a void card (cancelled credit cannot be revived) and a non-positive
        amount. A credited card is (re)activated — a previously exhausted/``redeemed``
        card becomes redeemable again now that it carries a balance. Returns ``None``
        when the card isn't in the caller's scope (→ 404).
        """
        card = await self.get_by_id(card_id, user_id)
        if not card:
            return None
        if (card.status or ACTIVE) == VOID:
            raise GiftCardError("This gift card has been cancelled")
        amount = quantize_money(amount or 0)
        if amount <= 0:
            raise GiftCardError("amount must be greater than 0")
        new_balance = quantize_money(quantize_money(card.balance or 0) + amount)
        card.balance = new_balance
        card.status = ACTIVE
        self._record(card, entry_type, amount, new_balance, transaction_id=transaction_id)
        await self.db.commit()
        await self.db.refresh(card)
        logger.info(
            "Gift card %s %s by %.2f → balance %.2f", card.id, entry_type, amount, new_balance
        )
        return card

    async def list_ledger(self, card_id: int, user_id: str) -> list[GiftCardLedger]:
        """The card's management-movement audit rows, oldest first (owner-scoped)."""
        result = await self.db.execute(
            select(GiftCardLedger)
            .where(
                GiftCardLedger.gift_card_id == card_id,
                GiftCardLedger.user_id == str(user_id),
            )
            .order_by(GiftCardLedger.id)
        )
        return list(result.scalars().all())
