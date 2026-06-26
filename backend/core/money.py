"""Decimal money helpers — the single source of truth for monetary arithmetic.

All money math in app code should run through this module so that totals, VAT,
discounts and gateway amounts never inherit IEEE-754 float drift (the classic
``round(2.675, 2) == 2.67`` trap, and reconciliation/QR-total mismatches that
follow from it). Amounts are :class:`~decimal.Decimal`, rounded **half-up** to
two places (banker's rounding is *not* what a customer-facing till expects).

The Saudi Riyal (SAR) subdivides into 100 *halalas*. Payment gateways (Moyasar)
charge in the smallest currency unit — integer halalas — so a riyal amount must
convert to/from halalas without losing a penny.

The :class:`Money` SQLAlchemy column type stores amounts as ``Numeric(12, 2)``
and re-quantizes on both bind and result, so a value round-trips penny-exact
even on SQLite (which maps ``NUMERIC`` to a REAL/float affinity).
"""
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal
from typing import Optional, Union

from sqlalchemy import Numeric
from sqlalchemy.types import TypeDecorator

# What callers may hand us: ints, floats (legacy float columns / JSON), strings
# (form input), or already-Decimal values.
Number = Union[int, float, str, Decimal]

HALALAS_PER_RIYAL = 100
TWO_PLACES = Decimal("0.01")


def to_decimal(value: Optional[Number]) -> Optional[Decimal]:
    """Coerce ``value`` to :class:`Decimal` without binary-float artifacts.

    Floats are routed through ``str()`` first so ``0.1`` becomes ``Decimal("0.1")``
    rather than ``Decimal("0.1000000000000000055...")``. ``None`` passes through
    as ``None`` (a missing amount, not zero).
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    # str() gives the shortest round-trippable repr for a float, and is exact for
    # ints and decimal strings.
    return Decimal(str(value))


def quantize_money(value: Number, rounding: str = ROUND_HALF_UP) -> Decimal:
    """Round ``value`` to two decimal places, half-up by default."""
    return to_decimal(value).quantize(TWO_PLACES, rounding=rounding)


def floor_units(amount: Number, rate: Number) -> int:
    """Multiply ``amount`` by ``rate`` in exact Decimal and floor to a whole unit.

    Whole-unit accruals (loyalty points, ``amount * points_per_sar``) floor the
    product to an integer. Doing the multiply in IEEE-754 float first lets drift
    turn an exact ``29.00`` into ``28.999…`` so a plain ``int()`` truncates a
    point away (``int(0.29 * 100) == 28``). Routing the product through
    :class:`Decimal` keeps the boundary exact, while a genuine fraction still
    floors toward zero (``floor_units(4.35, 10) == 43``).
    """
    product = to_decimal(amount) * to_decimal(rate)
    return int(product.to_integral_value(rounding=ROUND_FLOOR))


def to_halalas(value: Number) -> int:
    """Convert a riyal amount to integer halalas (the gateway charge unit)."""
    halalas = quantize_money(value) * HALALAS_PER_RIYAL
    # The value is already 2dp, so this is an integer; round to be safe against
    # any residual fractional halala before truncating.
    return int(halalas.to_integral_value(rounding=ROUND_HALF_UP))


def from_halalas(halalas: int) -> Decimal:
    """Convert integer halalas back to a 2dp riyal :class:`Decimal`."""
    return (Decimal(int(halalas)) / HALALAS_PER_RIYAL).quantize(TWO_PLACES)


class Money(TypeDecorator):
    """A ``Numeric(12, 2)`` column that always reads/writes a 2dp Decimal.

    SQLite has no native fixed-point type and gives ``NUMERIC`` columns a REAL
    (float) affinity, so a naive ``Numeric`` round-trips through a float and can
    drift. Quantizing on both bind and result keeps stored money penny-exact on
    every backend while keeping ``Numeric(12, 2)`` as the declared/DDL type.
    """

    impl = Numeric(12, 2)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return quantize_money(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return quantize_money(value)
