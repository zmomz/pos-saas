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
    "buyer_vat_no": "الرقم الضريبي للمشتري",
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
    buyer_vat,
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
    # B2B buyer tax block (PRN-02): render the buyer VAT only when present, so B2C
    # invoices stay unchanged.
    if buyer_vat:
        line(f"{_L['buyer_vat_no']}: {buyer_vat}")
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
    buyer_vat,
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
    if buyer_vat:
        pdf.cell(0, 6, _safe(f"Buyer VAT: {buyer_vat}"), ln=True)
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


# ---------------------------------------------------------------------------
# PRN-08 — Subscription invoice (agent → client), A4 PDF, always-Arabic.
# A non-POS billing document (no ZATCA QR/stamp): the white-label agent (seller)
# bills the client merchant (buyer) for one subscription period. VAT is rendered
# only when the agent is VAT-registered (today agents carry no VAT number, so the
# block is omitted), per the PRN-08 design.
# ---------------------------------------------------------------------------
_LSUB = {
    "title": "فاتورة اشتراك",
    "title_en": "Subscription Invoice",
    "seller": "البائع (الوكيل)",
    "buyer": "المشتري (العميل)",
    "vat_no": "الرقم الضريبي",
    "buyer_vat_no": "الرقم الضريبي للمشتري",
    "invoice_no": "رقم الفاتورة",
    "date": "التاريخ",
    "period": "فترة الاشتراك",
    "cycle": "دورة الفوترة",
    "fee": "رسوم الاشتراك",
    "vat": "ضريبة القيمة المضافة",
    "grand_total": "الإجمالي شامل الضريبة",
    "status": "حالة الدفع",
    "sar": "ر.س",
    "not_tax_note": "فاتورة اشتراك في الخدمة",
}

# Cycle + payment-status code → Arabic label (best-effort; unknown codes pass
# through unchanged so the document never blanks).
_SUB_CYCLE_AR = {"monthly": "شهري", "yearly": "سنوي"}
_SUB_STATUS_AR = {
    "paid": "مدفوعة",
    "manual": "مدفوعة (يدوي)",
    "stripe": "مدفوعة (بطاقة)",
    "active": "مدفوعة",
}


def subscription_invoice_rows(
    *,
    seller_name: str,
    seller_vat: str,
    buyer_name: str,
    buyer_vat: str,
    invoice_number: str,
    issue_date: str,
    period_start: str,
    period_end: str,
    billing_cycle: str,
    fee: float,
    vat_amount: float,
    payment_status: str,
    payment_method: str,
) -> List[tuple]:
    """Build the ordered required sections of a PRN-08 subscription invoice.

    Returns a list of ``(kind, label, value)`` tuples in render order. Pure and
    deterministic so the document's required-section contract (seller / buyer /
    period / fee / VAT-if-registered / payment status) is unit-testable without
    parsing PDF bytes.
    """
    total_amount = float(fee or 0) + float(vat_amount or 0)
    cycle_label = _SUB_CYCLE_AR.get(billing_cycle or "", billing_cycle or "")
    status_label = _SUB_STATUS_AR.get(payment_status or "", payment_status or "")
    if payment_method:
        status_label = f"{status_label} — {payment_method}"

    rows: List[tuple] = []
    rows.append(("seller", _LSUB["seller"], seller_name))
    # Seller VAT (PRN-08: only when the agent is VAT-registered).
    if seller_vat:
        rows.append(("seller_vat", _LSUB["vat_no"], seller_vat))
    rows.append(("buyer", _LSUB["buyer"], buyer_name))
    if buyer_vat:
        rows.append(("buyer_vat", _LSUB["buyer_vat_no"], buyer_vat))
    rows.append(("invoice_no", _LSUB["invoice_no"], invoice_number))
    rows.append(("date", _LSUB["date"], issue_date))
    rows.append(("period", _LSUB["period"], f"{period_start} — {period_end}"))
    rows.append(("cycle", _LSUB["cycle"], cycle_label))
    rows.append(("fee", _LSUB["fee"], f"{float(fee or 0):.2f} {_LSUB['sar']}"))
    # VAT line only when the agent charged VAT (registered seller).
    if vat_amount:
        rows.append(("vat", _LSUB["vat"], f"{float(vat_amount):.2f} {_LSUB['sar']}"))
    rows.append(("total", _LSUB["grand_total"], f"{total_amount:.2f} {_LSUB['sar']}"))
    rows.append(("status", _LSUB["status"], status_label))
    return rows


def _render_subscription_arabic(rows: List[tuple]) -> bytes:
    from fpdf import FPDF

    pdf = FPDF(unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_font(_FONT_FAMILY, "", _FONT_PATH, uni=True)
    pdf.add_page()

    def line(text, size=11, align="R", h=7, ln=True):
        pdf.set_font(_FONT_FAMILY, "", size)
        pdf.cell(0, h, _shape(text), ln=ln, align=align)

    line(_LSUB["title"], size=16, align="C", h=10)
    line(_LSUB["not_tax_note"], size=9, align="C", h=6)
    pdf.ln(2)
    # RTL rows render as "value  :label" so the colon hugs the Arabic label.
    for _kind, label, value in rows:
        line(f"{value}  :{label}")
    return bytes(pdf.output())


def _render_subscription_latin(rows: List[tuple]) -> bytes:
    from fpdf import FPDF

    # Latin labels mirror the Arabic order for the no-font fallback.
    _LAT = {
        "seller": "Seller (Agent)",
        "seller_vat": "VAT No",
        "buyer": "Buyer (Client)",
        "buyer_vat": "Buyer VAT No",
        "invoice_no": "Invoice No",
        "date": "Date",
        "period": "Subscription period",
        "cycle": "Billing cycle",
        "fee": "Subscription fee",
        "vat": "VAT",
        "total": "Total (incl. VAT)",
        "status": "Payment status",
    }

    pdf = FPDF(unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, _safe(_LSUB["title_en"]), ln=True, align="C")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 6, _safe("Subscription invoice (not a tax invoice)"), ln=True, align="C")
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 10)
    for kind, _label, value in rows:
        pdf.cell(0, 6, _safe(f"{_LAT.get(kind, kind)}: {value}"), ln=True)
    return bytes(pdf.output())


def subscription_invoice_pdf_bytes(
    *,
    seller_name: str,
    buyer_name: str,
    invoice_number: str,
    issue_date: str,
    period_start: str,
    period_end: str,
    billing_cycle: str,
    fee: float,
    seller_vat: str = "",
    buyer_vat: str = "",
    vat_amount: float = 0.0,
    payment_status: str = "paid",
    payment_method: str = "",
) -> bytes:
    """Render a PRN-08 subscription invoice (agent → client) to PDF bytes.

    Always-Arabic via the bundled Amiri font when available, else a Latin-1-safe
    fallback. Raises RuntimeError if fpdf2 is absent.
    """
    try:
        import fpdf  # noqa: F401
    except ImportError as exc:  # pragma: no cover - dependency is in requirements
        raise RuntimeError("fpdf2 is not installed; cannot render PDF") from exc

    rows = subscription_invoice_rows(
        seller_name=seller_name,
        seller_vat=seller_vat,
        buyer_name=buyer_name,
        buyer_vat=buyer_vat,
        invoice_number=invoice_number,
        issue_date=issue_date,
        period_start=period_start,
        period_end=period_end,
        billing_cycle=billing_cycle,
        fee=fee,
        vat_amount=vat_amount,
        payment_status=payment_status,
        payment_method=payment_method,
    )
    if _arabic_available():
        try:
            return _render_subscription_arabic(rows)
        except Exception as exc:  # pragma: no cover - fall back rather than fail
            logger.warning("Arabic subscription PDF render failed (%s); using Latin fallback", exc)
    return _render_subscription_latin(rows)


# ---------------------------------------------------------------------------
# F-072 — Generic report → PDF renderer (RPT-10). A shared, RTL-aware tabular
# renderer sitting alongside the invoice renderer so *every* /reports/* endpoint
# can answer ``?format=pdf``. Reports render **always-Arabic** (consistent with
# the fiscal-Arabic rule) using the bundled Amiri font + reshaper/bidi when
# available, falling back to a Latin-1-safe layout so a valid PDF is always
# produced even if the shaping stack is missing.
#
# The caller passes a language-neutral description of the report:
#   • title   — an ``(arabic, english)`` pair for the document heading
#   • meta    — a list of ``((label_ar, label_en), value)`` summary lines
#   • sections — a list of dicts: ``{heading: (ar, en) | None, columns:
#     [(ar, en), …], rows: [[cell, …], …], aligns: ["R"|"C"|"L", …] | None}``
# Cells are plain strings (numbers / names) and are language-neutral; only the
# chrome (title / labels / column headers) carries both languages.
# ---------------------------------------------------------------------------


def _pair(value, idx: int) -> str:
    """Pick the arabic (idx 0) or english (idx 1) half of a label pair.

    Tolerates a plain string (used for both languages) so callers may pass a
    single language-neutral header where no translation is needed.
    """
    if isinstance(value, (tuple, list)):
        return str(value[idx]) if len(value) > idx else str(value[0])
    return "" if value is None else str(value)


def _fit(value: object, width_mm: float) -> str:
    """Truncate a cell so it roughly fits ``width_mm`` (≈1.9mm per glyph at 9pt)."""
    s = "" if value is None else str(value)
    max_chars = max(3, int(width_mm / 1.9))
    return s if len(s) <= max_chars else s[: max_chars - 1] + "…"


def _render_report_arabic(title, meta, sections) -> bytes:
    from fpdf import FPDF

    pdf = FPDF(unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.set_margins(10, 10, 10)
    pdf.add_font(_FONT_FAMILY, "", _FONT_PATH, uni=True)
    pdf.add_page()
    epw = pdf.w - pdf.l_margin - pdf.r_margin

    pdf.set_font(_FONT_FAMILY, "", 16)
    pdf.cell(0, 10, _shape(_pair(title, 0)), ln=True, align="C")
    pdf.ln(1)

    pdf.set_font(_FONT_FAMILY, "", 10)
    for label, value in meta or []:
        # RTL line: "value  :label" so the colon hugs the Arabic label.
        pdf.cell(0, 6, _shape(f"{value}  :{_pair(label, 0)}"), ln=True, align="R")

    for section in sections:
        pdf.ln(2)
        heading = section.get("heading")
        if heading:
            pdf.set_font(_FONT_FAMILY, "", 12)
            pdf.cell(0, 7, _shape(_pair(heading, 0)), ln=True, align="R")
        columns = section["columns"]
        rows = section.get("rows", [])
        n = len(columns)
        widths = section.get("widths") or [round(epw / n, 2)] * n
        # RTL: reverse the column order so logical column 0 sits on the right.
        order = list(range(n))[::-1]

        pdf.set_font(_FONT_FAMILY, "", 9)
        for i in order:
            pdf.cell(widths[i], 7, _shape(_pair(columns[i], 0)), border=1, align="C")
        pdf.ln()

        if not rows:
            pdf.cell(epw, 6, _shape("لا توجد بيانات"), border=1, align="C", ln=True)
            continue
        for row in rows:
            for i in order:
                pdf.cell(widths[i], 6, _shape(_fit(row[i], widths[i])), border=1, align="R")
            pdf.ln()

    return bytes(pdf.output())


def _render_report_latin(title, meta, sections) -> bytes:
    from fpdf import FPDF

    pdf = FPDF(unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.set_margins(10, 10, 10)
    pdf.add_page()
    epw = pdf.w - pdf.l_margin - pdf.r_margin

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, _safe(_pair(title, 1)), ln=True, align="C")
    pdf.ln(1)

    pdf.set_font("Helvetica", "", 10)
    for label, value in meta or []:
        pdf.cell(0, 6, _safe(f"{_pair(label, 1)}: {value}"), ln=True)

    for section in sections:
        pdf.ln(2)
        heading = section.get("heading")
        if heading:
            pdf.set_font("Helvetica", "B", 12)
            pdf.cell(0, 7, _safe(_pair(heading, 1)), ln=True)
        columns = section["columns"]
        rows = section.get("rows", [])
        n = len(columns)
        widths = section.get("widths") or [round(epw / n, 2)] * n

        pdf.set_font("Helvetica", "B", 9)
        for i in range(n):
            pdf.cell(widths[i], 7, _safe(_pair(columns[i], 1)), border=1, align="C")
        pdf.ln()

        pdf.set_font("Helvetica", "", 9)
        if not rows:
            pdf.cell(epw, 6, _safe("No data"), border=1, align="C", ln=True)
            continue
        for row in rows:
            for i in range(n):
                pdf.cell(widths[i], 6, _safe(_fit(row[i], widths[i])), border=1, align="R")
            pdf.ln()

    return bytes(pdf.output())


def report_pdf_bytes(*, title, meta=None, sections) -> bytes:
    """Render a generic tabular report to PDF bytes (F-072).

    ``title`` is an ``(arabic, english)`` pair, ``meta`` a list of
    ``(label_pair, value)`` summary lines, ``sections`` a list of table dicts
    (see the module note above). Always-Arabic via the bundled Amiri font when
    available, else a Latin-1-safe fallback. Raises RuntimeError if fpdf2 is
    absent.
    """
    try:
        import fpdf  # noqa: F401
    except ImportError as exc:  # pragma: no cover - dependency is in requirements
        raise RuntimeError("fpdf2 is not installed; cannot render PDF") from exc

    if _arabic_available():
        try:
            return _render_report_arabic(title, meta or [], sections)
        except Exception as exc:  # pragma: no cover - fall back rather than fail
            logger.warning("Arabic report PDF render failed (%s); using Latin fallback", exc)
    return _render_report_latin(title, meta or [], sections)


def invoice_pdf_bytes(
    *,
    seller_name: str,
    seller_vat: str,
    buyer_name: str,
    invoice_number: str,
    buyer_vat: str = "",
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
        buyer_vat=buyer_vat,
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
