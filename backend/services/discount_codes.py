import logging
import secrets
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.discount_codes import DiscountCodes
from services.discounts import _as_naive, compute_discount_amount

logger = logging.getLogger(__name__)

# Unambiguous alphabet for the human-typed/scannable part of a code (no 0/O/1/I).
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CODE_LEN = 10


class DiscountCodeError(ValueError):
    """A unique discount code failed redemption (mapped to HTTP 400).

    Raised when a code is unknown, already redeemed (one-shot), outside its
    validity window, or below its ``min_purchase`` floor.
    """


def _mint_code() -> str:
    """A random, hard-to-guess, unambiguous code (uppercase, no lookalikes)."""
    return "".join(secrets.choice(_ALPHABET) for _ in range(_CODE_LEN))


class DiscountCodesService:
    """Service layer for single-use unique discount codes (ISSUE-059)."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_batch(
        self,
        *,
        user_id: str,
        count: int,
        type: str,
        value: float,
        min_purchase: Optional[float] = None,
        starts_at: Optional[datetime] = None,
        ends_at: Optional[datetime] = None,
        client_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Mint ``count`` unique codes in one batch and persist them.

        Returns ``{batch_id, count, codes:[DiscountCodes]}``. Each code is unique
        within the batch; uniqueness across the owner's existing codes is best-effort
        (collisions on a 10-char 32-symbol space are astronomically unlikely).

        ARC-05 / ISSUE-193: ``client_id`` is the resolved tenant scope's owning
        client, stamped on every minted code as advisory metadata for parity with
        the core tables — isolation stays bounded by ``user_id`` (see
        ``get_by_code``), not this column; a payload value is never trusted.
        """
        batch_id = uuid.uuid4().hex
        seen: set[str] = set()
        objs: List[DiscountCodes] = []
        for _ in range(count):
            code = _mint_code()
            while code in seen:
                code = _mint_code()
            seen.add(code)
            obj = DiscountCodes(
                user_id=str(user_id),
                client_id=client_id,
                batch_id=batch_id,
                code=code,
                type=type,
                value=value,
                min_purchase=min_purchase,
                redeemed=False,
                starts_at=starts_at,
                ends_at=ends_at,
            )
            self.db.add(obj)
            objs.append(obj)
        await self.db.commit()
        for obj in objs:
            await self.db.refresh(obj)
        logger.info("Minted discount-code batch %s (%d codes) for %s", batch_id, count, user_id)
        return {"batch_id": batch_id, "count": len(objs), "codes": objs}

    async def get_by_code(self, code: str, user_id: str) -> Optional[DiscountCodes]:
        """Look up a unique code within the owner's scope (case-insensitive)."""
        result = await self.db.execute(
            select(DiscountCodes).where(
                func.lower(DiscountCodes.code) == (code or "").strip().lower(),
                DiscountCodes.user_id == str(user_id),
            )
        )
        return result.scalars().first()

    async def validate(
        self,
        code: str,
        subtotal: float,
        user_id: str,
        now: Optional[datetime] = None,
    ) -> DiscountCodes:
        """Validate a single-use code for an order subtotal (FIN-09). Read-only.

        Enforces, server-side: the code exists in the caller's scope, has not been
        redeemed (one-shot), falls inside its validity window, and the order meets
        ``min_purchase``. Raises ``DiscountCodeError`` (→ HTTP 400) otherwise.
        Does **not** consume the use — call ``consume`` for that, atomically with
        the sale, so a rolled-back sale never spends the code (mirrors
        ``DiscountsService.validate``/``consume``).

        ``now`` is injectable so the window check is deterministic in tests.
        """
        dc = await self.get_by_code(code, user_id)
        if not dc:
            raise DiscountCodeError("Invalid discount code")
        if dc.redeemed:
            raise DiscountCodeError("This code has already been redeemed")
        reference = _as_naive(now) if now is not None else datetime.now()
        starts_at = _as_naive(dc.starts_at)
        ends_at = _as_naive(dc.ends_at)
        if starts_at is not None and reference < starts_at:
            raise DiscountCodeError("This code is not active yet")
        if ends_at is not None and reference > ends_at:
            raise DiscountCodeError("This code has expired")
        if dc.min_purchase and float(subtotal) < float(dc.min_purchase):
            raise DiscountCodeError(
                f"Minimum purchase of {float(dc.min_purchase):.2f} required"
            )
        return dc

    async def consume(
        self, code_id: int, user_id: str, now: Optional[datetime] = None
    ) -> bool:
        """Atomically consume the single use with a conditional UPDATE. No commit.

        Flips ``redeemed`` False→True only while it is still False, so two
        concurrent redemptions of the same code cannot both succeed (the one-shot
        is enforced in SQL, not by a read-then-write race). Runs inside the
        caller's transaction (the sale), so the consumption commits with the sale
        and rolls back if the sale fails. Returns ``True`` when the use was
        consumed, ``False`` when the code was already redeemed.
        """
        reference = _as_naive(now) if now is not None else datetime.now()
        result = await self.db.execute(
            update(DiscountCodes)
            .where(
                DiscountCodes.id == code_id,
                DiscountCodes.user_id == str(user_id),
                DiscountCodes.redeemed.is_(False),
            )
            .values(redeemed=True, redeemed_at=reference)
        )
        return (result.rowcount or 0) > 0

    async def redeem(
        self,
        code: str,
        subtotal: float,
        user_id: str,
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Validate + consume a unique code in one committed step (standalone path).

        For direct redemption that is not folded into a sale. Validates read-only,
        consumes the single use with the conditional UPDATE, and commits. Raises
        ``DiscountCodeError`` (→ HTTP 400) on any failure, including an
        already-redeemed code. When consumption belongs to a sale, use
        ``validate`` + ``consume`` so the code is spent iff the sale commits
        (FIN-09).

        ``now`` is injectable so the window check is deterministic in tests.
        """
        reference = _as_naive(now) if now is not None else datetime.now()
        dc = await self.validate(code, subtotal, user_id, now=reference)
        if not await self.consume(dc.id, user_id, now=reference):
            await self.db.rollback()
            raise DiscountCodeError("This code has already been redeemed")
        await self.db.commit()

        amount = compute_discount_amount(dc, float(subtotal))
        return {"code": dc.code, "type": dc.type, "value": dc.value, "discount_amount": amount}
