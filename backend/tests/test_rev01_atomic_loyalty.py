"""REV-01 — atomic guarded decrement/increment for the loyalty balance.

``redeem_points`` used to be read-check-write (read balance, check
``available >= points``, write an *absolute* ``points_balance = new_balance``),
so two concurrent redemptions for the same customer could both pass the check
and both write the same lowered value — double-spending real monetary discount.
``accrue_points`` had the milder lost-update variant (concurrent accruals
overwrite each other's absolute ``current + earned`` write, under-crediting).

These tests pin the same atomic-conditional-UPDATE invariant DAT-01 gave stock:
N concurrent redemptions on a balance of K let *exactly* ``floor(K/points)``
succeed, and N concurrent accruals all land (no lost update). The ledger row
(FIN-08) must still be written for every movement.
"""
import asyncio

import pytest

from conftest import make_client_account
from core.database import db_manager
from models.loyalty_points import Loyalty_points
from models.loyalty_programs import Loyalty_programs
from models.loyalty_transactions import Loyalty_transactions
from services.loyalty import accrue_points, redeem_points
from sqlalchemy import func, select


def _program(**kw):
    """A detached program row; redeem/accrue only read its rate attributes."""
    defaults = dict(redemption_rate=0.5, min_redemption_points=0, points_per_sar=1.0)
    defaults.update(kw)
    return Loyalty_programs(name="Rewards", is_active=True, **defaults)


async def _seed_balance(user_id, client_id, customer_id, balance):
    async with db_manager.async_session_maker() as db:
        db.add(
            Loyalty_points(
                user_id=user_id,
                client_id=client_id,
                customer_id=customer_id,
                points_balance=balance,
                total_earned=balance,
                total_redeemed=0,
            )
        )
        await db.commit()


async def _read(user_id, customer_id):
    async with db_manager.async_session_maker() as db:
        row = (
            await db.execute(
                select(Loyalty_points).where(
                    Loyalty_points.user_id == user_id,
                    Loyalty_points.customer_id == customer_id,
                )
            )
        ).scalar_one_or_none()
        redeemed = (
            await db.execute(
                select(func.count()).select_from(Loyalty_transactions).where(
                    Loyalty_transactions.user_id == user_id,
                    Loyalty_transactions.customer_id == customer_id,
                    Loyalty_transactions.type == "redeemed",
                )
            )
        ).scalar_one()
        earned_pts = (
            await db.execute(
                select(func.coalesce(func.sum(Loyalty_transactions.points), 0)).where(
                    Loyalty_transactions.user_id == user_id,
                    Loyalty_transactions.customer_id == customer_id,
                    Loyalty_transactions.type == "earned",
                )
            )
        ).scalar_one()
        return row, redeemed, earned_pts


async def _redeem_one(user_id, client_id, customer_id, points, program) -> bool:
    """One redemption in its own transaction. True if it deducted."""
    async with db_manager.async_session_maker() as db:
        try:
            await redeem_points(
                db,
                user_id=user_id,
                client_id=client_id,
                customer_id=customer_id,
                points=points,
                program=program,
                max_discount=10_000.0,
            )
            await db.commit()
            return True
        except ValueError:
            await db.rollback()
            return False


async def _accrue_one(user_id, client_id, customer_id, amount, program):
    async with db_manager.async_session_maker() as db:
        await accrue_points(
            db,
            user_id=user_id,
            client_id=client_id,
            customer_id=customer_id,
            total_amount=amount,
            program=program,
        )
        await db.commit()


async def test_concurrent_redemptions_cannot_double_spend(client):
    """K=100, N=10 parallel 60-point redemptions -> exactly one succeeds, balance=40."""
    user, token, client_id = await make_client_account(client)
    await _seed_balance(user["id"], client_id, customer_id=7, balance=100)
    program = _program()

    results = await asyncio.gather(
        *[_redeem_one(user["id"], client_id, 7, 60, program) for _ in range(10)]
    )

    assert sum(results) == 1  # floor(100 / 60)
    row, redeemed_rows, _ = await _read(user["id"], 7)
    assert row.points_balance == 40  # never negative, never double-spent
    assert row.total_redeemed == 60
    assert redeemed_rows == 1  # one ledger row per real movement (FIN-08)


async def test_redeem_insufficient_balance_raises_and_leaves_balance(client):
    user, token, client_id = await make_client_account(client)
    await _seed_balance(user["id"], client_id, customer_id=8, balance=30)
    program = _program()

    async with db_manager.async_session_maker() as db:
        with pytest.raises(ValueError):
            await redeem_points(
                db,
                user_id=user["id"],
                client_id=client_id,
                customer_id=8,
                points=50,
                program=program,
                max_discount=10_000.0,
            )
        await db.rollback()

    row, redeemed_rows, _ = await _read(user["id"], 8)
    assert row.points_balance == 30  # untouched
    assert redeemed_rows == 0


async def test_concurrent_accruals_do_not_lose_updates(client):
    """N=10 parallel accruals of 10 points each on an existing row -> balance 100."""
    user, token, client_id = await make_client_account(client)
    await _seed_balance(user["id"], client_id, customer_id=9, balance=0)
    program = _program()

    await asyncio.gather(
        *[_accrue_one(user["id"], client_id, 9, 10.0, program) for _ in range(10)]
    )

    row, _, earned_pts = await _read(user["id"], 9)
    assert row.points_balance == 100  # no lost update
    assert row.total_earned == 100
    assert earned_pts == 100  # one ledger row per accrual, summing to the balance
