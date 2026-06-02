"""Arabic-Indic numeral formatting helpers (SRS L10N-03).

The "receipts/quotations always Arabic" rule (SRS §7) means the server-rendered
fiscal documents must read as Arabic regardless of the caller's UI language —
and that includes the numerals: amounts and quantities are rendered with
Arabic-Indic digits (٠١٢٣٤٥٦٧٨٩) and the Arabic decimal separator (٫).

Identifiers (invoice/quotation numbers, VAT registration numbers) are codes, not
prose, so they are intentionally left in Western digits — converting them would
change the value a reader types back into a system.
"""
from typing import Union

# Western 0-9 -> Arabic-Indic ٠-٩
_ARABIC_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")

# Arabic decimal separator (U+066B) and thousands separator (U+066C).
_ARABIC_DECIMAL = "٫"
_ARABIC_THOUSANDS = "٬"


def to_arabic_digits(text: Union[str, int, float]) -> str:
    """Convert every Western digit in ``text`` to its Arabic-Indic equivalent."""
    return str(text).translate(_ARABIC_DIGITS)


def format_money_ar(amount: float, decimals: int = 2) -> str:
    """Render a monetary amount with Arabic-Indic digits and separators.

    e.g. ``1234.5`` -> ``"١٬٢٣٤٫٥٠"``. Used by the always-Arabic invoice and
    quotation documents so the totals read natively in Arabic.
    """
    try:
        value = float(amount)
    except (TypeError, ValueError):
        value = 0.0
    western = f"{value:,.{decimals}f}"  # e.g. "1,234.50"
    western = western.replace(",", _ARABIC_THOUSANDS).replace(".", _ARABIC_DECIMAL)
    return western.translate(_ARABIC_DIGITS)
