"""Loyalty accrual + redemption logic for the POS pay flow (Phase E).

The generic `/api/v1/production/loyalty/*` endpoints expose standalone
earn/redeem/balance operations, but until now a *sale* never touched the
loyalty ledger — accrual and redemption were orphaned from `create_transaction`.

This module provides the real business logic, wired into the **atomic** POS
sale. Every function here operates on the caller's `AsyncSession` **without
committing**: the POS router commits the sale, the inventory deduction, the
point redemption and the point accrual together, so a failed sale never moves
the loyalty ledger and an accrued point is never lost to a rolled-back sale.

Redemption is modelled as a **discount** on the order (the same way the
standalone `/loyalty/redeem` endpoint reports a `discount_value`): redeemed
points reduce the taxable amount before VAT. Accrual earns
`floor(total_amount * points_per_sar)` points for the named customer.
"""
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.money import quantize_money, to_decimal

from models.loyalty_points import Loyalty_points
from models.loyalty_programs import Loyalty_programs
from models.loyalty_transactions import Loyalty_transactions

logger = logging.getLogger(__name__)


def record_ledger_movement(
    db: AsyncSession,
    *,
    user_id: str,
    client_id: Optional[int],
    customer_id: int,
    type: str,
    points: int,
    description: Optional[str] = None,
) -> None:
    """Append one row to the ``loyalty_transactions`` ledger (no commit).

    This is the single place the POS sale path records a point movement, so the
    ledger the admin "Points History" tab and the expiry engine read
    (``compute_usable_balance``) stays in lock-step with the ``loyalty_points``
    balance. ``points`` is the positive magnitude; the sign is implied by
    ``type`` ("earned"/"add" credit, "redeemed"/"deduct" debit). The caller owns
    the transaction and commits the ledger row atomically with the balance change
    and the sale, so a rolled-back sale leaves no orphan ledger row.
    """
    db.add(
        Loyalty_transactions(
            user_id=user_id,
            client_id=client_id,
            customer_id=customer_id,
            type=type,
            points=points,
            description=description,
        )
    )


@dataclass
class RedemptionResult:
    points_redeemed: int
    discount_value: Decimal
    remaining_balance: int


@dataclass
class AccrualResult:
    points_earned: int
    new_balance: int


async def get_active_program(
    db: AsyncSession, user_id: str
) -> Optional[Loyalty_programs]:
    """Return THE active loyalty program for the merchant, if any.

    The single-active invariant is enforced on every write (see
    ``enforce_single_active_program``), so at most one row is active per tenant.
    The ``id`` ordering is a deterministic tiebreaker that keeps the POS stable
    even if a legacy tenant still carries more than one active row: it always
    resolves to the most recently created program.
    """
    result = await db.execute(
        select(Loyalty_programs)
        .where(
            Loyalty_programs.user_id == user_id,
            Loyalty_programs.is_active == True,  # noqa: E712
        )
        .order_by(Loyalty_programs.id.desc())
    )
    return result.scalars().first()


async def enforce_single_active_program(
    db: AsyncSession, user_id: str, keep_id: Optional[int]
) -> None:
    """Deactivate every active program for ``user_id`` except ``keep_id`` (no commit).

    The single authoritative active program is the one being written
    (``keep_id``); any other previously-active program for the tenant is flipped
    to ``is_active = False`` so exactly one program is active at a time. The
    caller owns the transaction and commits. ``keep_id`` may be ``None`` (e.g.
    before a row has an id), in which case every active row is deactivated.
    """
    conditions = [
        Loyalty_programs.user_id == user_id,
        Loyalty_programs.is_active == True,  # noqa: E712
    ]
    if keep_id is not None:
        conditions.append(Loyalty_programs.id != keep_id)
    await db.execute(
        update(Loyalty_programs).where(*conditions).values(is_active=False)
    )


async def _get_balance_row(
    db: AsyncSession, user_id: str, customer_id: int
) -> Optional[Loyalty_points]:
    result = await db.execute(
        select(Loyalty_points).where(
            Loyalty_points.user_id == user_id,
            Loyalty_points.customer_id == customer_id,
        )
    )
    return result.scalar_one_or_none()


async def redeem_points(
    db: AsyncSession,
    *,
    user_id: str,
    client_id: int,
    customer_id: int,
    points: int,
    program: Loyalty_programs,
    max_discount: float,
) -> RedemptionResult:
    """Validate and deduct redeemed points (no commit).

    Raises ``ValueError`` with a human message on any rule violation; the POS
    router converts these to HTTP 400 so the whole sale rolls back.

    ``max_discount`` caps the redemption value so it can never exceed the order
    subtotal (which would otherwise produce a negative taxable amount).
    """
    if points <= 0:
        raise ValueError("redeem_points must be positive")

    rate = program.redemption_rate or 0.0
    if rate <= 0:
        raise ValueError("Loyalty program has no redemption rate configured")

    min_points = program.min_redemption_points or 0
    if points < min_points:
        raise ValueError(
            f"Minimum redemption is {min_points} points (requested {points})"
        )

    row = await _get_balance_row(db, user_id, customer_id)
    available = (row.points_balance or 0) if row else 0
    if available < points:
        raise ValueError(
            f"Insufficient points. Available: {available}, requested: {points}"
        )

    discount_value = quantize_money(to_decimal(points) * to_decimal(rate))
    if discount_value > quantize_money(max_discount):
        raise ValueError(
            f"Redemption value {discount_value:.2f} exceeds order subtotal "
            f"{quantize_money(max_discount):.2f}"
        )

    new_balance = available - points
    await db.execute(
        update(Loyalty_points)
        .where(Loyalty_points.id == row.id)
        .values(
            points_balance=new_balance,
            total_redeemed=(row.total_redeemed or 0) + points,
        )
    )
    record_ledger_movement(
        db,
        user_id=user_id,
        client_id=client_id,
        customer_id=customer_id,
        type="redeemed",
        points=points,
        description="Redeemed on sale",
    )
    return RedemptionResult(
        points_redeemed=points,
        discount_value=discount_value,
        remaining_balance=new_balance,
    )


async def accrue_points(
    db: AsyncSession,
    *,
    user_id: str,
    client_id: int,
    customer_id: int,
    total_amount: float,
    program: Loyalty_programs,
) -> Optional[AccrualResult]:
    """Earn points for the customer based on the sale total (no commit).

    Upserts the customer's `loyalty_points` row. Returns ``None`` when the
    program earns nothing (no `points_per_sar`).
    """
    rate = program.points_per_sar or 0.0
    if rate <= 0:
        return None

    points_earned = int(total_amount * rate)
    if points_earned <= 0:
        return None

    row = await _get_balance_row(db, user_id, customer_id)
    if row:
        new_balance = (row.points_balance or 0) + points_earned
        await db.execute(
            update(Loyalty_points)
            .where(Loyalty_points.id == row.id)
            .values(
                points_balance=new_balance,
                total_earned=(row.total_earned or 0) + points_earned,
            )
        )
    else:
        new_balance = points_earned
        db.add(
            Loyalty_points(
                user_id=user_id,
                client_id=client_id,
                customer_id=customer_id,
                points_balance=points_earned,
                total_earned=points_earned,
                total_redeemed=0,
            )
        )
    record_ledger_movement(
        db,
        user_id=user_id,
        client_id=client_id,
        customer_id=customer_id,
        type="earned",
        points=points_earned,
        description="Earned on sale",
    )
    return AccrualResult(points_earned=points_earned, new_balance=new_balance)
