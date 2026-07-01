"""Retail-scale variable-measure barcode parsing (ISSUE-230, Integrations).

A price-computing / weighing scale (the deli, produce, butchery counter) prints
a **variable-measure EAN-13** for each weighed item. Unlike a fixed catalog
barcode the value it carries changes on every weigh, so the code never matches a
stored ``products.barcode`` exactly — the POS has to recognise the *format*, lift
the item code (PLU) out to resolve the product, and read the embedded value.

Layout — the widely used GS1 in-store "5-5" variable-measure EAN-13 (13 digits)::

    2 IIIII V VVVVV C
    │ │     │ │     └─ d13  EAN-13 check digit (validated)
    │ │     │ └─────── d8..12  5-digit embedded value
    │ │     └───────── d7   the value's own internal check digit (ignored here)
    │ └─────────────── d2..6  5-digit item code (PLU)
    └───────────────── d1   flag ``2`` — GS1 in-store / restricted-distribution

The embedded value's *meaning* is decided by the resolved product, not the
barcode, so this parser stays interpretation-agnostic and returns the raw
integer:

* a **weighted** product → grams (``value / 1000`` kg = the line quantity);
* any other product → halalas (``value / 100`` = the line's total price, the
  scale having already done the price×weight maths).

``item_prefix`` (flag + item code, the leading 6 chars) is the stable key a
merchant's catalog barcode shares across every weigh, so the resolver matches a
product by comparing the first six characters of its stored barcode.

The parser is deliberately strict: a code that is not 13 digits, does not start
with ``2``, or fails the EAN-13 checksum is **not** a scale barcode (returns
``None``) so an ordinary 13-digit product EAN is never mis-parsed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# GS1 in-store / restricted-distribution flag digit that opens a variable-measure
# barcode. Kept as a constant so the resolver and tests agree on the family.
SCALE_FLAG = "2"


def ean13_check_digit(twelve: str) -> str:
    """The EAN-13 check digit for a 12-digit body (odd positions ×1, even ×3)."""
    if len(twelve) != 12 or not twelve.isdigit():
        raise ValueError("ean13_check_digit expects 12 digits")
    total = 0
    for i, ch in enumerate(twelve):
        # 1-indexed position: odd → weight 1, even → weight 3.
        total += int(ch) * (3 if (i + 1) % 2 == 0 else 1)
    return str((10 - (total % 10)) % 10)


@dataclass(frozen=True)
class ScaleBarcode:
    """A parsed variable-measure scale barcode."""

    raw: str
    item_prefix: str  # flag + item code (leading 6 chars) — the catalog match key
    item_code: str    # the 5-digit PLU
    value: int        # the raw 5-digit embedded value (grams or halalas)


def parse_scale_barcode(barcode: Optional[str]) -> Optional[ScaleBarcode]:
    """Parse ``barcode`` as a variable-measure scale EAN-13, or ``None``.

    Returns ``None`` — meaning "not a scale barcode, resolve it normally" — for
    anything that is not 13 digits, does not carry the in-store flag, or fails the
    EAN-13 checksum.
    """
    code = (barcode or "").strip()
    if len(code) != 13 or not code.isdigit():
        return None
    if code[0] != SCALE_FLAG:
        return None
    if ean13_check_digit(code[:12]) != code[12]:
        return None
    return ScaleBarcode(
        raw=code,
        item_prefix=code[:6],
        item_code=code[1:6],
        value=int(code[7:12]),
    )
