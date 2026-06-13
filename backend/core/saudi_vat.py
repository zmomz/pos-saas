"""Saudi VAT (TRN) registration-number validation.

A Saudi VAT registration number — the Tax Registration Number (TRN) issued by
ZATCA and printed on tax invoices — is exactly **15 digits** that begin and end
with ``3`` (e.g. ``300000000000003``). It is a code, not an arithmetic quantity,
so it is stored and validated as a string of digits.

This is shared, vertical-agnostic vocabulary: suppliers, customers (buyer VAT)
and the seller's own registration all use the same format.
"""
from typing import Optional

SAUDI_VAT_LENGTH = 15


def normalize_vat_number(value: Optional[str]) -> Optional[str]:
    """Trim surrounding whitespace; treat blank/None as 'no VAT number' (None)."""
    if value is None:
        return None
    trimmed = str(value).strip()
    return trimmed or None


def validate_saudi_vat(value: Optional[str]) -> Optional[str]:
    """Return the normalized 15-digit VAT number, or ``None`` if blank.

    Raises :class:`ValueError` with a clear, actionable message when the value is
    present but malformed.
    """
    normalized = normalize_vat_number(value)
    if normalized is None:
        return None
    if not normalized.isdigit() or len(normalized) != SAUDI_VAT_LENGTH:
        raise ValueError(
            f"VAT number must be exactly {SAUDI_VAT_LENGTH} digits"
        )
    if not (normalized.startswith("3") and normalized.endswith("3")):
        raise ValueError("VAT number must start and end with 3")
    return normalized
