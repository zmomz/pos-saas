"""ESC/POS thermal receipt builder (Phase E).

Generates a raw ESC/POS byte stream for an 80mm thermal printer: printer init,
an **always-Arabic** receipt body rendered as a raster bitmap, an embedded ZATCA
QR code (the same TLV base64 carried on the on-screen invoice), a feed and a
partial cut. The bytes are returned base64-encoded so the browser frontend can
stream them to a WebUSB / Web Bluetooth printer (see
`frontend/src/lib/thermalPrint.ts`).

Arabic rendering (SRS L10N-06 / PRN-01 — F-021). The fiscal invariant is that
*every* fiscal document — including the most-printed one, the thermal receipt —
renders in **Arabic, RTL, with Arabic-Indic digits, regardless of the UI
language**. ESC/POS code-page text cannot guarantee correct connected Arabic
glyphs (it depends on the printer's installed Arabic firmware and mangles
non-ASCII under a CP437 fallback), so the receipt body is drawn server-side to a
1-bit bitmap using the bundled Amiri OFL font with `arabic_reshaper` +
`python-bidi` (the same pipeline as the always-Arabic A4 PDF) and emitted via the
GS v 0 raster command. This prints identical, correctly-shaped Arabic on any
printer that supports raster bit-images (effectively all modern thermal units).
The ZATCA QR is still emitted as a native QR symbol (best scannability). If the
rendering libraries or font are unavailable at runtime, a degraded ASCII text
fallback keeps the stream valid (OPS-08 graceful degradation).
"""
import base64
import logging
import os

from core.formatting import format_money_ar, to_arabic_digits

logger = logging.getLogger(__name__)

ESC = 0x1B
GS = 0x1D

# Bundled Arabic OFL font (shared with the A4 PDF renderer).
_FONT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets",
    "fonts",
    "Amiri-Regular.ttf",
)

# 80mm thermal heads are 576 dots wide at 203dpi (a multiple of 8, so no row
# padding is needed for the raster command).
_WIDTH_PX = 576

# Always-Arabic receipt labels (mirrors the A4 invoice's label set).
_L = {
    "store": "المتجر",
    "vat_no": "الرقم الضريبي",
    "tax_invoice": "فاتورة ضريبية",
    # F-059: a non-fiscal proforma ("check") the customer reviews BEFORE paying. It
    # carries no QR and no stamp so it can never be mistaken for a tax invoice.
    "proforma": "فاتورة مبدئية",
    "invoice_no": "رقم الفاتورة",
    "date": "التاريخ",
    "subtotal": "المجموع الفرعي",
    "discount": "الخصم",
    "vat": "ضريبة القيمة المضافة",
    "grand_total": "الإجمالي شامل الضريبة (ر.س)",
    # F-061: service charge collected on top of the tax-invoice total, OUTSIDE the
    # VAT base (exactly like a tip). Shown only when a service charge applies.
    "service_charge": "رسوم الخدمة",
    # POS-13 (F-012): tip / gratuity collected on top of the tax-invoice total, and
    # the amount the customer actually paid (total + service charge + tip). Shown
    # only when tipped / a service charge applies.
    "tip": "البقشيش",
    "total_paid": "المبلغ المدفوع (ر.س)",
    "thanks": "شكراً لزيارتكم",
    # F-057: kitchen order ticket (KOT) — printed per prep-station for a fired
    # course. It is an operational ticket, NOT a fiscal document: modifiers are
    # grouped under each course and **no prices ever appear**.
    "kot": "تذكرة المطبخ",
    "station": "المحطة",
    "order": "الطلب",
    "table": "الطاولة",
    "fired": "أُرسلت",
}


class EscPosBuilder:
    """Accumulates an ESC/POS command stream."""

    def __init__(self) -> None:
        self._buf = bytearray()
        # ESC @ — initialise printer (clears modes, restores defaults).
        self._buf += bytes([ESC, ord("@")])

    # ---- low level ----
    def raw(self, data: bytes) -> "EscPosBuilder":
        self._buf += data
        return self

    def text(self, value: str) -> "EscPosBuilder":
        # CP437-safe fallback so unknown glyphs never abort the stream.
        self._buf += value.encode("cp437", errors="replace")
        return self

    def line(self, value: str = "") -> "EscPosBuilder":
        return self.text(value).raw(b"\n")

    # ---- formatting ----
    def align(self, mode: str) -> "EscPosBuilder":
        """ESC a n — 0 left, 1 center, 2 right."""
        n = {"left": 0, "center": 1, "right": 2}.get(mode, 0)
        return self.raw(bytes([ESC, ord("a"), n]))

    def bold(self, on: bool) -> "EscPosBuilder":
        """ESC E n — emphasised on/off."""
        return self.raw(bytes([ESC, ord("E"), 1 if on else 0]))

    def double_size(self, on: bool) -> "EscPosBuilder":
        """GS ! n — select character size (double width+height when on)."""
        return self.raw(bytes([GS, ord("!"), 0x11 if on else 0x00]))

    def feed(self, lines: int = 1) -> "EscPosBuilder":
        """ESC d n — feed n lines."""
        return self.raw(bytes([ESC, ord("d"), max(0, min(lines, 255))]))

    def cut(self) -> "EscPosBuilder":
        """GS V 66 0 — partial cut (feed then cut)."""
        return self.raw(bytes([GS, ord("V"), 66, 0]))

    def kick_drawer(self, pin: int = 0, on_ms: int = 25, off_ms: int = 250) -> "EscPosBuilder":
        """ESC p m t1 t2 — pulse the cash-drawer kick connector (HW-04).

        Emits ``0x1B 0x70`` followed by the connector pin (0 or 1) and the on/off
        pulse durations (in 2ms units, clamped to a byte). A drawer wired to the
        printer's RJ11 kick port opens when this pulse prints — sent on cash sales
        so the till opens automatically.
        """
        m = 1 if pin else 0
        t1 = max(0, min(on_ms, 255))
        t2 = max(0, min(off_ms, 255))
        return self.raw(bytes([ESC, ord("p"), m, t1, t2]))

    def qr(self, data: str, size: int = 6) -> "EscPosBuilder":
        """Embed a QR code using the GS ( k model-2 command sequence."""
        payload = data.encode("utf-8")
        # Function 165: select QR model 2.
        self.raw(bytes([GS, ord("("), ord("k"), 4, 0, 49, 65, 50, 0]))
        # Function 167: module size.
        self.raw(bytes([GS, ord("("), ord("k"), 3, 0, 49, 67, max(1, min(size, 16))]))
        # Function 169: error-correction level (48..51 = L,M,Q,H); use M.
        self.raw(bytes([GS, ord("("), ord("k"), 3, 0, 49, 69, 49]))
        # Function 180: store the QR data in the symbol buffer.
        length = len(payload) + 3
        pl, ph = length & 0xFF, (length >> 8) & 0xFF
        self.raw(bytes([GS, ord("("), ord("k"), pl, ph, 49, 80, 48]))
        self.raw(payload)
        # Function 181: print the stored symbol.
        self.raw(bytes([GS, ord("("), ord("k"), 3, 0, 49, 81, 48]))
        return self

    def raster_image(self, img) -> "EscPosBuilder":
        """Emit a 1-bit PIL image via the GS v 0 raster bit-image command.

        ``GS v 0 m xL xH yL yH [data]`` prints a raster image where every set bit
        is a black dot. The image is converted to mode "1"; in that mode a pixel
        value of 0 is black, so a black pixel maps to a set bit (MSB-first, eight
        pixels per byte). The width is padded to a byte boundary if needed.
        """
        img = img.convert("1")
        w, h = img.size
        if w % 8:
            from PIL import Image

            padded = Image.new("1", (w + (8 - w % 8), h), 1)
            padded.paste(img, (0, 0))
            img = padded
            w = img.size[0]
        bytes_per_row = w // 8
        pixels = img.load()
        data = bytearray()
        for y in range(h):
            for xb in range(bytes_per_row):
                byte = 0
                base = xb * 8
                for bit in range(8):
                    if pixels[base + bit, y] == 0:  # 0 == black in mode "1"
                        byte |= 0x80 >> bit
                data.append(byte)
        xl, xh = bytes_per_row & 0xFF, (bytes_per_row >> 8) & 0xFF
        yl, yh = h & 0xFF, (h >> 8) & 0xFF
        self.raw(bytes([GS, ord("v"), ord("0"), 0, xl, xh, yl, yh]))
        self.raw(bytes(data))
        return self

    def build(self) -> bytes:
        return bytes(self._buf)


def _money(value: float) -> str:
    return f"{value or 0:.2f}"


def _arabic_render_available() -> bool:
    """True when the bundled font + Arabic shaping + PIL are all importable."""
    if not os.path.exists(_FONT_PATH):
        return False
    try:
        import arabic_reshaper  # noqa: F401
        from bidi.algorithm import get_display  # noqa: F401
        from PIL import Image, ImageDraw, ImageFont  # noqa: F401
    except ImportError:
        return False
    return True


def _shape(text: object) -> str:
    """Reshape + bidi-reorder a string for correct connected/RTL Arabic."""
    import arabic_reshaper
    from bidi.algorithm import get_display

    s = "" if text is None else str(text)
    return get_display(arabic_reshaper.reshape(s))


def _item_display_name(item: dict) -> str:
    """Prefer the Arabic product name on the always-Arabic receipt (PRN-01)."""
    name_ar = (item.get("name_ar") or "").strip() if isinstance(item, dict) else ""
    if name_ar:
        return name_ar
    return str(item.get("name", "") if isinstance(item, dict) else "")


def _render_receipt_image(
    *,
    seller_name: str,
    vat_number: str,
    invoice_number: str,
    issue_date: str,
    line_items: list,
    subtotal: float,
    discount: float,
    vat_amount: float,
    total_amount: float,
    tip_amount: float = 0,
    service_charge: float = 0,
    proforma: bool = False,
):
    """Render the always-Arabic receipt body to a 1-bit PIL image (RTL).

    When ``proforma`` (F-059) the header reads *فاتورة مبدئية* instead of *فاتورة
    ضريبية* so the non-fiscal check the customer reviews before paying is never
    mistaken for a tax invoice.
    """
    from PIL import Image, ImageDraw, ImageFont

    f_title = ImageFont.truetype(_FONT_PATH, 40)
    f_big = ImageFont.truetype(_FONT_PATH, 30)
    f_norm = ImageFont.truetype(_FONT_PATH, 26)
    f_small = ImageFont.truetype(_FONT_PATH, 24)

    margin = 12
    # Generous canvas; cropped to the rendered height before emitting.
    est_h = 640 + len(line_items or []) * 150
    img = Image.new("1", (_WIDTH_PX, est_h), 1)  # 1 == white background
    draw = ImageDraw.Draw(img)
    y = margin

    def row_h(font, pad: int = 8) -> int:
        ascent, descent = font.getmetrics()
        return ascent + descent + pad

    def center(text, font) -> None:
        nonlocal y
        t = _shape(text)
        w = draw.textlength(t, font=font)
        draw.text(((_WIDTH_PX - w) / 2, y), t, font=font, fill=0)
        y += row_h(font)

    def right(text, font) -> None:
        nonlocal y
        t = _shape(text)
        w = draw.textlength(t, font=font)
        draw.text((_WIDTH_PX - margin - w, y), t, font=font, fill=0)
        y += row_h(font)

    def lr(right_text, left_text, font) -> None:
        # Arabic label on the right (RTL), the code/amount on the left.
        nonlocal y
        rt = _shape(right_text)
        rw = draw.textlength(rt, font=font)
        draw.text((_WIDTH_PX - margin - rw, y), rt, font=font, fill=0)
        draw.text((margin, y), str(left_text), font=font, fill=0)
        y += row_h(font)

    def rule() -> None:
        nonlocal y
        y += 2
        draw.line([(margin, y), (_WIDTH_PX - margin, y)], fill=0, width=2)
        y += 12

    # ---- header ----
    center(seller_name or _L["store"], f_title)
    lr(_L["vat_no"], vat_number or "-", f_small)
    center(_L["proforma"] if proforma else _L["tax_invoice"], f_big)
    rule()
    lr(_L["invoice_no"], invoice_number or "-", f_small)
    lr(_L["date"], issue_date or "-", f_small)
    rule()

    # ---- line items ----
    for item in line_items or []:
        name = _item_display_name(item)
        qty = item.get("quantity", 1)
        price = float(item.get("price", 0) or 0)
        item_disc = float(item.get("discount", 0) or 0)
        amount = price * qty - item_disc
        right(name, f_norm)
        # qty × unit = amount, in Arabic-Indic digits, left-aligned (numeric LTR).
        amounts = (
            f"{to_arabic_digits(qty)} × {format_money_ar(price)}"
            f" = {format_money_ar(amount)}"
        )
        draw.text((margin, y), amounts, font=f_small, fill=0)
        y += row_h(f_small)
    rule()

    # ---- totals ----
    lr(_L["subtotal"], format_money_ar(subtotal), f_norm)
    if discount:
        lr(_L["discount"], "-" + format_money_ar(discount), f_norm)
    lr(_L["vat"], format_money_ar(vat_amount), f_norm)
    lr(_L["grand_total"], format_money_ar(total_amount), f_big)
    # F-061/POS-13 (F-012): the service charge and the tip both sit OUTSIDE the
    # tax-invoice total above; show each, plus the amount the customer actually paid
    # (total + service charge + tip), so the printed document matches what was
    # charged. Each line is omitted when its amount is zero.
    if service_charge:
        lr(_L["service_charge"], format_money_ar(service_charge), f_norm)
    if tip_amount:
        lr(_L["tip"], format_money_ar(tip_amount), f_norm)
    if service_charge or tip_amount:
        lr(
            _L["total_paid"],
            format_money_ar(total_amount + service_charge + tip_amount),
            f_big,
        )
    rule()

    return img.crop((0, 0, _WIDTH_PX, min(y + margin, est_h)))


def _render_footer_image():
    """Render the always-Arabic 'thank you' footer to a 1-bit PIL image."""
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype(_FONT_PATH, 26)
    ascent, descent = font.getmetrics()
    h = ascent + descent + 16
    img = Image.new("1", (_WIDTH_PX, h), 1)
    draw = ImageDraw.Draw(img)
    t = _shape(_L["thanks"])
    w = draw.textlength(t, font=font)
    draw.text(((_WIDTH_PX - w) / 2, 8), t, font=font, fill=0)
    return img


def _append_text_fallback(
    b: "EscPosBuilder",
    *,
    seller_name,
    vat_number,
    invoice_number,
    issue_date,
    line_items,
    subtotal,
    discount,
    vat_amount,
    total_amount,
    tip_amount: float = 0,
    service_charge: float = 0,
    proforma: bool = False,
    width: int,
) -> None:  # pragma: no cover - only hit in a degraded environment
    """Degraded ASCII receipt body when Arabic rendering is unavailable.

    Keeps the stream valid (OPS-08) so a printer still produces a receipt with the
    scannable ZATCA QR even if the font/shaping libraries are missing at runtime.
    """
    b.align("center").bold(True).double_size(True)
    b.line(seller_name or "Store")
    b.double_size(False)
    b.line("PROFORMA" if proforma else "TAX INVOICE")
    b.line(f"VAT: {vat_number or '-'}")
    b.bold(False)
    b.line("-" * width)
    b.align("left")
    b.line(f"No: {invoice_number}")
    b.line(f"Date: {issue_date}")
    b.line("-" * width)
    for item in line_items or []:
        name = _item_display_name(item)[: width - 12]
        qty = item.get("quantity", 1)
        price = float(item.get("price", 0) or 0)
        item_disc = float(item.get("discount", 0) or 0)
        amount = price * qty - item_disc
        b.line(name)
        b.line(f"{qty} x {_money(price)} = {_money(amount)}".rjust(width))
    b.line("-" * width)
    b.line("Subtotal:".ljust(width - 12) + _money(subtotal).rjust(12))
    if discount:
        b.line("Discount:".ljust(width - 12) + ("-" + _money(discount)).rjust(12))
    b.line("VAT:".ljust(width - 12) + _money(vat_amount).rjust(12))
    b.bold(True)
    b.line("TOTAL (SAR):".ljust(width - 12) + _money(total_amount).rjust(12))
    b.bold(False)
    if service_charge:
        b.line("Service:".ljust(width - 12) + _money(service_charge).rjust(12))
    if tip_amount:
        b.line("Tip:".ljust(width - 12) + _money(tip_amount).rjust(12))
    if service_charge or tip_amount:
        b.bold(True)
        b.line(
            "PAID (SAR):".ljust(width - 12)
            + _money(total_amount + service_charge + tip_amount).rjust(12)
        )
        b.bold(False)
    b.line("-" * width)


def build_receipt(
    *,
    seller_name: str,
    vat_number: str,
    invoice_number: str,
    issue_date: str,
    line_items: list,
    subtotal: float,
    discount: float,
    vat_amount: float,
    total_amount: float,
    tip_amount: float = 0,
    service_charge: float = 0,
    zatca_qr: str = "",
    proforma: bool = False,
    width: int = 42,
    open_drawer: bool = False,
) -> bytes:
    """Render a transaction as an ESC/POS byte stream for an 80mm printer.

    The body is the always-Arabic raster receipt (SRS L10N-06 / PRN-01). When
    ``open_drawer`` is true (a cash sale) the stream carries a cash-drawer kick
    pulse (HW-04) so a connected till opens as the receipt prints.

    When ``proforma`` (F-059) the body is headed *فاتورة مبدئية* and **no QR is
    emitted regardless of ``zatca_qr``** — a check is non-fiscal and must carry no
    QR and no stamp, so it can never be mistaken for a tax invoice.
    """
    b = EscPosBuilder()

    if open_drawer:
        # Pulse the drawer first so the till opens for the cashier immediately.
        b.kick_drawer()

    rendered = False
    if _arabic_render_available():
        try:
            body = _render_receipt_image(
                seller_name=seller_name,
                vat_number=vat_number,
                invoice_number=invoice_number,
                issue_date=issue_date,
                line_items=line_items,
                subtotal=subtotal,
                discount=discount,
                vat_amount=vat_amount,
                total_amount=total_amount,
                tip_amount=tip_amount,
                service_charge=service_charge,
                proforma=proforma,
            )
            b.align("center").raster_image(body)
            rendered = True
        except Exception:  # pragma: no cover - degraded environment
            logger.warning("Arabic thermal render failed; using text fallback", exc_info=True)

    if not rendered:  # pragma: no cover - degraded environment
        _append_text_fallback(
            b,
            seller_name=seller_name,
            vat_number=vat_number,
            invoice_number=invoice_number,
            issue_date=issue_date,
            line_items=line_items,
            subtotal=subtotal,
            discount=discount,
            vat_amount=vat_amount,
            total_amount=total_amount,
            tip_amount=tip_amount,
            service_charge=service_charge,
            proforma=proforma,
            width=width,
        )

    # A proforma is non-fiscal: never emit a QR even if one was passed (F-059).
    if zatca_qr and not proforma:
        b.align("center").qr(zatca_qr)

    # Footer (always Arabic when rendering is available).
    if rendered:
        try:
            b.align("center").raster_image(_render_footer_image())
        except Exception:  # pragma: no cover - degraded environment
            b.align("center").line("Thank you")
    else:  # pragma: no cover - degraded environment
        b.align("center").line("Thank you")

    b.feed(3).cut()
    return b.build()


def build_receipt_base64(**kwargs) -> str:
    """Convenience wrapper returning the receipt as a base64 string."""
    return base64.b64encode(build_receipt(**kwargs)).decode("ascii")


def _render_kot_image(
    *,
    station_name: str,
    order_ref: str,
    table_label: str,
    fired_at: str,
    courses: list,
):
    """Render an always-Arabic KOT body to a 1-bit PIL image (RTL) — F-057.

    Items are grouped under their course heading; each item shows only its
    quantity, name, modifier choices and any note — **never a price** (a kitchen
    ticket carries no money). ``courses`` is a list of
    ``{"course": str, "items": [{"name"/"name_ar", "qty", "notes", "modifiers": [str]}]}``.
    """
    from PIL import Image, ImageDraw, ImageFont

    f_title = ImageFont.truetype(_FONT_PATH, 42)
    f_course = ImageFont.truetype(_FONT_PATH, 32)
    f_item = ImageFont.truetype(_FONT_PATH, 34)
    f_small = ImageFont.truetype(_FONT_PATH, 24)

    margin = 12
    n_items = sum(len(c.get("items") or []) for c in courses or [])
    est_h = 360 + len(courses or []) * 60 + n_items * 130
    img = Image.new("1", (_WIDTH_PX, est_h), 1)
    draw = ImageDraw.Draw(img)
    y = margin

    def row_h(font, pad: int = 8) -> int:
        ascent, descent = font.getmetrics()
        return ascent + descent + pad

    def center(text, font) -> None:
        nonlocal y
        t = _shape(text)
        w = draw.textlength(t, font=font)
        draw.text(((_WIDTH_PX - w) / 2, y), t, font=font, fill=0)
        y += row_h(font)

    def right(text, font, indent: int = 0) -> None:
        nonlocal y
        t = _shape(text)
        w = draw.textlength(t, font=font)
        draw.text((_WIDTH_PX - margin - indent - w, y), t, font=font, fill=0)
        y += row_h(font)

    def lr(right_text, left_text, font) -> None:
        nonlocal y
        rt = _shape(right_text)
        rw = draw.textlength(rt, font=font)
        draw.text((_WIDTH_PX - margin - rw, y), rt, font=font, fill=0)
        draw.text((margin, y), str(left_text), font=font, fill=0)
        y += row_h(font)

    def rule() -> None:
        nonlocal y
        y += 2
        draw.line([(margin, y), (_WIDTH_PX - margin, y)], fill=0, width=2)
        y += 12

    # ---- header ----
    center(_L["kot"], f_title)
    center(station_name or _L["station"], f_course)
    rule()
    if order_ref:
        lr(_L["order"], order_ref, f_small)
    if table_label:
        lr(_L["table"], table_label, f_small)
    if fired_at:
        lr(_L["fired"], fired_at, f_small)
    rule()

    # ---- courses + items (no prices) ----
    for course in courses or []:
        right(course.get("course") or "", f_course)
        for item in course.get("items") or []:
            name = _item_display_name(item)
            qty = item.get("qty", 1)
            right(f"{to_arabic_digits(qty)} × {name}", f_item)
            for mod in item.get("modifiers") or []:
                right(f"+ {mod}", f_small, indent=28)
            note = (item.get("notes") or "").strip()
            if note:
                right(f"» {note}", f_small, indent=28)
        rule()

    return img.crop((0, 0, _WIDTH_PX, min(y + margin, est_h)))


def _append_kot_text_fallback(
    b: "EscPosBuilder",
    *,
    station_name: str,
    order_ref: str,
    table_label: str,
    courses: list,
    width: int,
) -> None:  # pragma: no cover - only hit in a degraded environment
    """Degraded ASCII KOT body when Arabic rendering is unavailable (OPS-08)."""
    b.align("center").bold(True).double_size(True)
    b.line("KOT")
    b.double_size(False)
    b.line(station_name or "Station")
    b.bold(False)
    b.line("-" * width)
    b.align("left")
    if order_ref:
        b.line(f"Order: {order_ref}")
    if table_label:
        b.line(f"Table: {table_label}")
    b.line("-" * width)
    for course in courses or []:
        b.bold(True)
        b.line(str(course.get("course") or ""))
        b.bold(False)
        for item in course.get("items") or []:
            name = _item_display_name(item)
            qty = item.get("qty", 1)
            b.line(f"{qty} x {name}")
            for mod in item.get("modifiers") or []:
                b.line(f"  + {mod}")
            note = (item.get("notes") or "").strip()
            if note:
                b.line(f"  » {note}")
        b.line("-" * width)


def build_kot(
    *,
    station_name: str,
    order_ref: str = "",
    table_label: str = "",
    fired_at: str = "",
    courses: list,
    width: int = 42,
) -> bytes:
    """Render a per-station Kitchen Order Ticket as an ESC/POS byte stream (F-057).

    The KOT is an **always-Arabic** operational ticket (the fiscal-document Arabic
    invariant applies to every printable): items are grouped under each course and
    carry **no prices** — a kitchen ticket never shows money. No QR, no stamp.
    """
    b = EscPosBuilder()
    rendered = False
    if _arabic_render_available():
        try:
            body = _render_kot_image(
                station_name=station_name,
                order_ref=order_ref,
                table_label=table_label,
                fired_at=fired_at,
                courses=courses,
            )
            b.align("center").raster_image(body)
            rendered = True
        except Exception:  # pragma: no cover - degraded environment
            logger.warning("Arabic KOT render failed; using text fallback", exc_info=True)

    if not rendered:  # pragma: no cover - degraded environment
        _append_kot_text_fallback(
            b,
            station_name=station_name,
            order_ref=order_ref,
            table_label=table_label,
            courses=courses,
            width=width,
        )

    b.feed(3).cut()
    return b.build()


def build_kot_base64(**kwargs) -> str:
    """Convenience wrapper returning the KOT as a base64 string."""
    return base64.b64encode(build_kot(**kwargs)).decode("ascii")
