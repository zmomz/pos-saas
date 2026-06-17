"""Numeral formatting helpers for the server-rendered fiscal documents.

Product decision (2026-06-18): **Western numerals everywhere, including
receipts** — overriding the old SRS L10N-03 "receipts always Arabic-Indic" rule.
The fiscal documents (thermal ESC/POS receipts, PDF invoices/quotations, Z/X
reports) keep their Arabic *text/labels* and the ``ر.س`` currency label, but the
digits and numeric separators are now Western (0-9, ``,`` thousands, ``.``
decimal).

These helpers are retained by name for back-compat with the document templates;
they no longer convert digits to Arabic-Indic.
"""
from typing import Union


def to_arabic_digits(text: Union[str, int, float]) -> str:
    """Pass ``text`` through unchanged as Western digits.

    Retained for back-compat. As of the 2026-06-18 Western-numerals decision this
    no longer converts Western digits to Arabic-Indic — it simply returns the
    stringified value.
    """
    return str(text)


def format_money_ar(amount: float, decimals: int = 2) -> str:
    """Render a monetary amount in Western grouped form.

    e.g. ``1234.5`` -> ``"1,234.50"``. Used by the fiscal documents so the totals
    print in Western numerals with Western separators (``,`` / ``.``), per the
    2026-06-18 Western-numerals decision. The Arabic ``ر.س`` currency label is
    added by the callers, not here.
    """
    try:
        value = float(amount)
    except (TypeError, ValueError):
        value = 0.0
    return f"{value:,.{decimals}f}"  # e.g. "1,234.50"
