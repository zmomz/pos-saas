"""Server-side PDF rendering for tax invoices (Phase 6 PDF deliverable).

Produces real ``application/pdf`` bytes from the invoice data via fpdf2 (pure
Python — no native deps), embedding the ZATCA fiscal QR.

The document is rendered **always-Arabic** (SRS §7) using a bundled OFL Arabic
font (Amiri) with ``arabic_reshaper`` + ``python-bidi`` so Arabic glyphs are
correctly shaped and right-to-left ordered. If the font or shaping libraries are
unavailable at runtime, it falls back to a Latin-1-safe transliteration so a
valid, downloadable PDF (with the scannable QR) is always produced.
"""
import base64
import io
import logging
import os
from typing import List, Optional

logger = logging.getLogger(__name__)

_FONT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets",
    "fonts",
    "Amiri-Regular.ttf",
)
_FONT_FAMILY = "Amiri"

# Arabic labels for the always-Arabic invoice (with English in parentheses where
# helpful for non-Arabic readers).
_L = {
    "tax_invoice": "فاتورة ضريبية",
    "seller": "البائع",
    "vat_no": "الرقم الضريبي",
    "buyer": "المشتري",
    "invoice_no": "رقم الفاتورة",
    "date": "التاريخ",
    "item": "الصنف",
    "qty": "الكمية",
    "price": "السعر",
    "total": "الإجمالي",
    "subtotal": "المجموع الفرعي",
    "discount": "الخصم",
    "vat": "ضريبة القيمة المضافة",
    "grand_total": "الإجمالي شامل الضريبة",
    "sar": "ر.س",
}


def _arabic_available() -> bool:
    if not os.path.exists(_FONT_PATH):
        return False
    try:
        import arabic_reshaper  # noqa: F401
        from bidi.algorithm import get_display  # noqa: F401
    except ImportError:
        return False
    return True


def _shape(text: object) -> str:
    """Reshape + bidi-reorder a string for correct Arabic rendering."""
    import arabic_reshaper
    from bidi.algorithm import get_display

    s = "" if text is None else str(text)
    return get_display(arabic_reshaper.reshape(s))


def _safe(text: object) -> str:
    """Coerce to a Latin-1-encodable string (fpdf2 core fonts are Latin-1)."""
    s = "" if text is None else str(text)
    return s.encode("latin-1", "replace").decode("latin-1")


def _render_arabic(
    *,
    seller_name,
    seller_vat,
    buyer_name,
    invoice_number,
    issue_date,
    line_items,
    subtotal,
    discount,
    vat_amount,
    total_amount,
    qr_png_base64,
) -> bytes:
    from fpdf import FPDF

    pdf = FPDF(unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_font(_FONT_FAMILY, "", _FONT_PATH, uni=True)
    pdf.add_page()

    def line(text, size=10, align="R", h=6, ln=True):
        pdf.set_font(_FONT_FAMILY, "", size)
        pdf.cell(0, h, _shape(text), ln=ln, align=align)

    line(_L["tax_invoice"], size=16, align="C", h=10)
    pdf.ln(2)
    line(f"{_L['seller']}: {seller_name}")
    line(f"{_L['vat_no']}: {seller_vat}")
    line(f"{_L['buyer']}: {buyer_name}")
    line(f"{_L['invoice_no']}: {invoice_number}")
    line(f"{_L['date']}: {issue_date}")
    pdf.ln(3)

    # Line-item table (RTL: total | price | qty | item).
    pdf.set_font(_FONT_FAMILY, "", 10)
    pdf.cell(35, 7, _shape(_L["total"]), border=1, align="C")
    pdf.cell(35, 7, _shape(_L["price"]), border=1, align="C")
    pdf.cell(25, 7, _shape(_L["qty"]), border=1, align="C")
    pdf.cell(90, 7, _shape(_L["item"]), border=1, align="C", ln=True)

    for item in line_items:
        name = item.get("name", "")
        qty = item.get("quantity", 0) or 0
        price = float(item.get("price", 0) or 0)
        pdf.cell(35, 7, _shape(f"{price * qty:.2f}"), border=1, align="R")
        pdf.cell(35, 7, _shape(f"{price:.2f}"), border=1, align="R")
        pdf.cell(25, 7, _shape(qty), border=1, align="C")
        pdf.cell(90, 7, _shape(name)[:60], border=1, align="R", ln=True)

    pdf.ln(2)
    for label, value in (
        (_L["subtotal"], subtotal),
        (_L["discount"], discount),
        (_L["vat"], vat_amount),
    ):
        pdf.set_font(_FONT_FAMILY, "", 10)
        pdf.cell(0, 6, _shape(f"{value:.2f} {_L['sar']}  :{label}"), align="R", ln=True)
    pdf.set_font(_FONT_FAMILY, "", 12)
    pdf.cell(0, 7, _shape(f"{total_amount:.2f} {_L['sar']}  :{_L['grand_total']}"), align="R", ln=True)

    if qr_png_base64:
        try:
            img = io.BytesIO(base64.b64decode(qr_png_base64))
            pdf.ln(4)
            pdf.image(img, w=35, h=35)
        except Exception as exc:  # pragma: no cover - QR is best-effort
            logger.warning("Embedding QR in PDF failed: %s", exc)

    return bytes(pdf.output())


def _render_latin(
    *,
    seller_name,
    seller_vat,
    buyer_name,
    invoice_number,
    issue_date,
    line_items,
    subtotal,
    discount,
    vat_amount,
    total_amount,
    qr_png_base64,
) -> bytes:
    from fpdf import FPDF

    pdf = FPDF(unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, _safe("TAX INVOICE"), ln=True, align="C")
    pdf.ln(2)

    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, _safe(f"Seller: {seller_name}"), ln=True)
    pdf.cell(0, 6, _safe(f"VAT No: {seller_vat}"), ln=True)
    pdf.cell(0, 6, _safe(f"Buyer: {buyer_name}"), ln=True)
    pdf.cell(0, 6, _safe(f"Invoice #: {invoice_number}"), ln=True)
    pdf.cell(0, 6, _safe(f"Date: {issue_date}"), ln=True)
    pdf.ln(3)

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(90, 7, _safe("Item"), border=1)
    pdf.cell(25, 7, _safe("Qty"), border=1, align="R")
    pdf.cell(35, 7, _safe("Price"), border=1, align="R")
    pdf.cell(35, 7, _safe("Total"), border=1, align="R", ln=True)

    pdf.set_font("Helvetica", "", 10)
    for item in line_items:
        name = item.get("name", "Item")
        qty = item.get("quantity", 0) or 0
        price = float(item.get("price", 0) or 0)
        pdf.cell(90, 7, _safe(name)[:45], border=1)
        pdf.cell(25, 7, _safe(qty), border=1, align="R")
        pdf.cell(35, 7, _safe(f"{price:.2f}"), border=1, align="R")
        pdf.cell(35, 7, _safe(f"{price * qty:.2f}"), border=1, align="R", ln=True)

    pdf.ln(2)
    pdf.set_font("Helvetica", "", 10)
    for label, value in (("Subtotal", subtotal), ("Discount", discount), ("VAT", vat_amount)):
        pdf.cell(150, 6, _safe(label), align="R")
        pdf.cell(35, 6, _safe(f"{value:.2f} SAR"), align="R", ln=True)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(150, 7, _safe("Total"), align="R")
    pdf.cell(35, 7, _safe(f"{total_amount:.2f} SAR"), align="R", ln=True)

    if qr_png_base64:
        try:
            img = io.BytesIO(base64.b64decode(qr_png_base64))
            pdf.ln(4)
            pdf.image(img, w=35, h=35)
        except Exception as exc:  # pragma: no cover - QR is best-effort
            logger.warning("Embedding QR in PDF failed: %s", exc)

    return bytes(pdf.output())


def invoice_pdf_bytes(
    *,
    seller_name: str,
    seller_vat: str,
    buyer_name: str,
    invoice_number: str,
    issue_date: str,
    line_items: List[dict],
    subtotal: float,
    discount: float,
    vat_amount: float,
    total_amount: float,
    qr_png_base64: Optional[str] = None,
) -> bytes:
    """Render a tax invoice to PDF bytes.

    Renders the always-Arabic layout with the bundled Amiri font + reshaper when
    available, else a Latin-1-safe fallback. Raises RuntimeError if fpdf2 is
    absent.
    """
    try:
        import fpdf  # noqa: F401
    except ImportError as exc:  # pragma: no cover - dependency is in requirements
        raise RuntimeError("fpdf2 is not installed; cannot render PDF") from exc

    kwargs = dict(
        seller_name=seller_name,
        seller_vat=seller_vat,
        buyer_name=buyer_name,
        invoice_number=invoice_number,
        issue_date=issue_date,
        line_items=line_items,
        subtotal=subtotal,
        discount=discount,
        vat_amount=vat_amount,
        total_amount=total_amount,
        qr_png_base64=qr_png_base64,
    )
    if _arabic_available():
        try:
            return _render_arabic(**kwargs)
        except Exception as exc:  # pragma: no cover - fall back rather than fail
            logger.warning("Arabic PDF render failed (%s); using Latin fallback", exc)
    return _render_latin(**kwargs)
