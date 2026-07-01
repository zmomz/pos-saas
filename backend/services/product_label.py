"""Product price/barcode label rendering for label printers (ISSUE-230, Integrations).

The second hardware-integration slice: a **label printer** (a Zebra-class device)
is driven by **ZPL** — a plain-text label language bracketed by ``^XA`` … ``^XZ``.
``render_product_label`` turns a catalog product into a small shelf / price label:
the product name, its price + currency (with a per-unit suffix for weighted
goods), and — when the product carries a catalog barcode — a Code 128 (``^BC``)
symbol the printer prints as a scannable barcode.

The renderer is deliberately a **pure function** (no DB, no I/O) so it is trivially
unit-tested and reused; the route layer fetches the owner-scoped product and hands
these fields in.

**Escaping.** ``^`` and ``~`` are ZPL command prefixes and ``_`` opens a hex
escape, so field data (the product name, the unit label) is sanitised before it is
placed inside a ``^FD`` … ``^FS`` field — an unescaped caret in a product name
would otherwise break out of the field and corrupt the label.
"""
from __future__ import annotations

from typing import Optional

# KSA-only tenancy (see billing model): labels price in Saudi riyals by default.
DEFAULT_CURRENCY = "SAR"


def _zpl_escape(text: Optional[str]) -> str:
    """Neutralise ZPL command characters in free-text field data.

    ``^`` / ``~`` open ZPL commands and ``_`` opens a hex escape; any of them in a
    product name would break out of the ``^FD`` field, so they are replaced with a
    space. Returns a stripped, single-line string.
    """
    cleaned = (text or "")
    for ch in ("^", "~", "_"):
        cleaned = cleaned.replace(ch, " ")
    # A newline would also terminate the field; collapse to spaces.
    cleaned = cleaned.replace("\r", " ").replace("\n", " ")
    return cleaned.strip()


def _price_line(price: float, currency: str, unit_label: Optional[str], is_weighted: bool) -> str:
    """The human-readable price string, e.g. ``14.50 SAR`` or ``9.00 SAR / kg``."""
    line = f"{float(price or 0):.2f} {currency}"
    suffix = _zpl_escape(unit_label) if unit_label else ("kg" if is_weighted else "")
    if suffix:
        line = f"{line} / {suffix}"
    return line


def render_product_label(
    *,
    name: str,
    price: float,
    barcode: Optional[str] = None,
    unit_label: Optional[str] = None,
    is_weighted: bool = False,
    currency: str = DEFAULT_CURRENCY,
    copies: int = 1,
) -> str:
    """Render a product shelf/price label as a ZPL program.

    The name and price always render as text; the Code 128 barcode block is emitted
    only when ``barcode`` is a non-empty code (a weighed/variable-measure product,
    or one simply lacking a code, prints a name+price label with no symbol).
    ``copies`` sets the ZPL print quantity (``^PQ``); values below 1 are treated as
    a single copy.
    """
    safe_name = _zpl_escape(name) or "(unnamed)"
    price_line = _price_line(price, currency, unit_label, is_weighted)
    qty = copies if isinstance(copies, int) and copies >= 1 else 1

    lines = [
        "^XA",
        "^PW400",              # 400-dot print width (~50mm @ 8dpmm)
        "^CF0,40",             # default font for the name
        f"^FO20,20^FD{safe_name}^FS",
        "^CF0,60",             # larger font for the price
        f"^FO20,70^FD{price_line}^FS",
    ]

    code = (barcode or "").strip()
    if code:
        code = _zpl_escape(code)
        lines += [
            "^BY2,2,90",                 # module width / ratio / height
            "^FO20,150^BCN,90,Y,N,N",    # Code 128, print interpretation line
            f"^FD{code}^FS",
        ]

    lines.append(f"^PQ{qty}")
    lines.append("^XZ")
    return "\n".join(lines)
