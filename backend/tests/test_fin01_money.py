"""FIN-01 — the shared Decimal money helper (core/money.py).

Money math must never inherit IEEE-754 float drift: half-up rounding has to be
exact, and riyal<->halala conversion (the smallest currency unit a gateway like
Moyasar charges in) must round-trip to the penny. These tests pin that behavior
through the public helpers, plus the penny-exact DB round-trip of the ``Money``
column type on the billing models.
"""
from decimal import Decimal

import pytest


def test_quantize_money_rounds_half_up_exactly():
    from core.money import quantize_money

    # The canonical float trap: 2.675 is actually 2.67499999...% in binary, so
    # round(2.675, 2) == 2.67. The Decimal helper must give the arithmetic answer.
    assert quantize_money("2.675") == Decimal("2.68")
    assert quantize_money(2.675) == Decimal("2.68")
    assert quantize_money(Decimal("2.5")) == Decimal("2.50")
    assert quantize_money("0.005") == Decimal("0.01")


def test_to_decimal_avoids_binary_float_artifacts():
    from core.money import to_decimal

    # Decimal(0.1) would be 0.1000000000000000055...; via str() it is exact.
    assert to_decimal(0.1) == Decimal("0.1")
    assert to_decimal("19.99") == Decimal("19.99")
    assert to_decimal(5) == Decimal("5")
    assert to_decimal(None) is None


def test_halala_conversion_round_trips_to_the_penny():
    from core.money import from_halalas, to_halalas

    assert to_halalas("19.99") == 1999
    assert to_halalas(100) == 10000
    assert to_halalas(0.1) == 10
    # round-trip: riyals -> halalas -> riyals is penny-exact
    assert from_halalas(to_halalas("123.45")) == Decimal("123.45")
    assert from_halalas(1999) == Decimal("19.99")


@pytest.mark.asyncio
async def test_billing_amount_round_trips_penny_exact_through_the_db():
    """A billing money column stores and returns a 2dp Decimal, penny-exact.

    Persists an amount that drifts under a REAL/float affinity, then reads it
    back in a fresh session: the value must come back as a Decimal equal to the
    quantized input (not a float, not 19.989999...).
    """
    from core.database import db_manager
    from models.subscription_payments import Subscription_payments

    amount = Decimal("19.99")
    async with db_manager.async_session_maker() as db:
        row = Subscription_payments(
            user_id="fin01-user",
            client_id=1,
            amount=amount,
            billing_cycle="monthly",
        )
        db.add(row)
        await db.commit()
        row_id = row.id

    async with db_manager.async_session_maker() as db:
        fetched = await db.get(Subscription_payments, row_id)

    assert isinstance(fetched.amount, Decimal)
    assert fetched.amount == Decimal("19.99")
