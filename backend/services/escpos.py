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

# The new Saudi Riyal sign (U+20C1) is absent from Amiri (and every shipping
# Arabic face), so we composite it from this single-glyph font when drawing the
# receipt image. The drawing helpers below switch to it for that one codepoint
# and fall back to the Arabic font for everything else — the bitmap analogue of
# the PDF's fallback font and the web build's unicode-range trick.
_RIYAL = "⃁"
_RIYAL_FONT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets",
    "fonts",
    "SaudiRiyal-Regular.ttf",
)
_riyal_font_cache: dict = {}


def _riyal_font(size: int):
    """Return (cached) the Saudi Riyal glyph font at ``size`` px."""
    font = _riyal_font_cache.get(size)
    if font is None:
        from PIL import ImageFont

        font = ImageFont.truetype(_RIYAL_FONT_PATH, size)
        _riyal_font_cache[size] = font
    return font


def _riyal_runs(text: str):
    """Split ``text`` into ``(is_riyal, run)`` segments of consecutive chars."""
    runs = []
    for ch in text:
        is_r = ch == _RIYAL
        if runs and runs[-1][0] == is_r:
            runs[-1][1] += ch
        else:
            runs.append([is_r, ch])
    return runs


def _mixed_width(draw, text: str, font) -> float:
    """``textlength`` that accounts for the Riyal glyph being drawn in its own font."""
    if _RIYAL not in text:
        return draw.textlength(text, font=font)
    rfont = _riyal_font(getattr(font, "size", 26))
    return sum(
        draw.textlength(run, font=(rfont if is_r else font))
        for is_r, run in _riyal_runs(text)
    )


def _draw_mixed(draw, xy, text: str, font, fill) -> None:
    """Draw ``text`` left-to-right, rendering U+20C1 with the Riyal font.

    Non-Riyal runs keep the Arabic font (and its shaping); the Riyal run is
    baseline-aligned by offsetting for the ascent difference between the fonts.
    Strings without the symbol take the plain single-font fast path so every
    other line is pixel-identical to before.
    """
    if _RIYAL not in text:
        draw.text(xy, text, font=font, fill=fill)
        return
    x, y = xy
    rfont = _riyal_font(getattr(font, "size", 26))
    dy = font.getmetrics()[0] - rfont.getmetrics()[0]  # align baselines
    for is_r, run in _riyal_runs(text):
        f = rfont if is_r else font
        draw.text((x, y + (dy if is_r else 0)), run, font=f, fill=fill)
        x += draw.textlength(run, font=f)

# 80mm thermal heads are 576 dots wide at 203dpi (a multiple of 8, so no row
# padding is needed for the raster command); 58mm heads have a 384-dot printable
# area. Both are multiples of 8. 80mm stays the default (ISSUE-046 / H26).
_WIDTH_PX = 576
_WIDTH_58MM_PX = 384
_PAPER_WIDTH_PX = {"80mm": _WIDTH_PX, "58mm": _WIDTH_58MM_PX}

# The ASCII text fallback's character width per paper size (degraded path only):
# ~12 dots/char at the fallback font, so 576/48 ≈ 42 chars on 80mm, 32 on 58mm.
_PAPER_TEXT_WIDTH = {"80mm": 42, "58mm": 32}

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
    "grand_total": "الإجمالي شامل الضريبة (⃁)",
    # F-061: service charge collected on top of the tax-invoice total, OUTSIDE the
    # VAT base (exactly like a tip). Shown only when a service charge applies.
    "service_charge": "رسوم الخدمة",
    # POS-13 (F-012): tip / gratuity collected on top of the tax-invoice total, and
    # the amount the customer actually paid (total + service charge + tip). Shown
    # only when tipped / a service charge applies.
    "tip": "البقشيش",
    "total_paid": "المبلغ المدفوع (⃁)",
    "thanks": "شكراً لزيارتكم",
    # ISSUE-075: a reprint of a past sale is NOT a fresh fiscal issuance. The
    # duplicate is stamped *نسخة — إعادة طباعة* ("copy — reprint") so the printed
    # receipt can never be mistaken for the original tax invoice.
    "reprint": "نسخة — إعادة طباعة",
    # F-057: kitchen order ticket (KOT) — printed per prep-station for a fired
    # course. It is an operational ticket, NOT a fiscal document: modifiers are
    # grouped under each course and **no prices ever appear**.
    "kot": "تذكرة المطبخ",
    "station": "المحطة",
    "order": "الطلب",
    "table": "الطاولة",
    "fired": "أُرسلت",
}

# H26 (F-?): the merchant's receipt template knobs. font_size is a coarse label
# ("small"/"medium"/"large") mapped to a multiplier over the base raster font
# sizes, so a bigger font produces a visibly taller bitmap.
_FONT_SCALE = {"small": 0.85, "medium": 1.0, "large": 1.2}


def _template_settings(template: object) -> dict:
    """Resolve a merchant receipt template (a plain dict or ``None``) into the
    render knobs honored by the builders, applying defaults.

    Booleans default to *on* (``show_logo``/``show_qr_code``) so a merchant with
    no template — or a template that leaves a field null — keeps the historical
    behaviour (logo title + QR emitted). ``header_text``/``footer_text`` default
    to empty (no extra line). ``font_size`` defaults to the unscaled size.
    """
    t = template if isinstance(template, dict) else {}

    def _flag(key: str) -> bool:
        v = t.get(key)
        return True if v is None else bool(v)

    fs = t.get("font_size")
    fs = fs.lower() if isinstance(fs, str) else "medium"
    ps = t.get("paper_size")
    ps = ps.lower() if isinstance(ps, str) else "80mm"
    return {
        "header_text": (t.get("header_text") or "").strip(),
        "footer_text": (t.get("footer_text") or "").strip(),
        "show_logo": _flag("show_logo"),
        "show_qr_code": _flag("show_qr_code"),
        # ARC-07: gates the itemized VAT line in the totals block. Defaults on so
        # the historical fiscal receipt is unchanged; the ZATCA QR (which carries
        # the tax amount) is never affected by this knob.
        "show_vat_details": _flag("show_vat_details"),
        "font_scale": _FONT_SCALE.get(fs, 1.0),
        # ISSUE-046: the printable raster width in dots, and the matching ASCII
        # column count for the degraded text fallback. Unknown sizes (e.g. "A4",
        # which never reaches the thermal path) fall back to 80mm.
        "width_px": _PAPER_WIDTH_PX.get(ps, _WIDTH_PX),
        "text_width": _PAPER_TEXT_WIDTH.get(ps, 42),
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


# The new Riyal sign (U+20C1) is too new for the bundled python-bidi's character
# database — it has no bidi class, which makes get_display() raise. We shape with
# the generic currency sign ¤ (U+00A4) as a stand-in (same ET bidi behaviour, so
# it orders identically) and restore the Riyal afterwards; the glyph is then
# composited by _draw_mixed. 1:1 substitution keeps every position intact.
_BIDI_RIYAL_PROXY = "¤"


def _shape(text: object) -> str:
    """Reshape + bidi-reorder a string for correct connected/RTL Arabic."""
    import arabic_reshaper
    from bidi.algorithm import get_display

    s = "" if text is None else str(text)
    if _RIYAL in s:
        shaped = get_display(arabic_reshaper.reshape(s.replace(_RIYAL, _BIDI_RIYAL_PROXY)))
        return shaped.replace(_BIDI_RIYAL_PROXY, _RIYAL)
    return get_display(arabic_reshaper.reshape(s))


def _item_display_name(item: dict) -> str:
    """Prefer the Arabic product name on the always-Arabic receipt (PRN-01)."""
    name_ar = (item.get("name_ar") or "").strip() if isinstance(item, dict) else ""
    if name_ar:
        return name_ar
    return str(item.get("name", "") if isinstance(item, dict) else "")


# Best-effort Arabic -> Latin romanization for the degraded CP437 text fallback
# (FIS-03). CP437 has no Arabic letters, so an un-transliterated name encodes to
# a run of '?' placeholders; romanizing keeps the line human-readable instead.
# Tashkeel (the U+064B-U+0652 diacritics) are dropped; unknown codepoints pass
# through unchanged.
_AR_TRANSLIT = {
    "ا": "a", "أ": "a", "إ": "i", "آ": "aa", "ء": "'", "ئ": "'", "ؤ": "w",
    "ب": "b", "ت": "t", "ث": "th", "ج": "j", "ح": "h", "خ": "kh",
    "د": "d", "ذ": "dh", "ر": "r", "ز": "z", "س": "s", "ش": "sh",
    "ص": "s", "ض": "d", "ط": "t", "ظ": "z", "ع": "'", "غ": "gh",
    "ف": "f", "ق": "q", "ك": "k", "ل": "l", "م": "m", "ن": "n",
    "ه": "h", "و": "w", "ي": "y", "ى": "a", "ة": "a", "ٱ": "a",
    "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
    "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
    "،": ",", "؛": ";", "؟": "?",
}
_AR_TASHKEEL = frozenset(chr(c) for c in range(0x064B, 0x0653)) | {"ـ"}


def transliterate_arabic(text: object) -> str:
    """Romanize Arabic text to printable ASCII for the CP437 fallback (FIS-03).

    Diacritics (tashkeel) and the tatweel are stripped; mapped letters become
    their Latin approximation; anything already-Latin is preserved as-is.
    """
    out = []
    for ch in str(text or ""):
        if ch in _AR_TASHKEEL:
            continue
        out.append(_AR_TRANSLIT.get(ch, ch))
    return "".join(out)


def _latin_display_name(item: dict) -> str:
    """ASCII-safe product name for the degraded CP437 text fallback (FIS-03).

    The always-Arabic raster path prefers ``name_ar``, but CP437 cannot encode
    Arabic. On the text fallback we therefore prefer the Latin ``name`` and, when
    only an Arabic name exists, transliterate it rather than letting CP437 mangle
    it into '?????'.
    """
    name = (item.get("name") or "").strip() if isinstance(item, dict) else ""
    if name:
        return name
    name_ar = (item.get("name_ar") or "").strip() if isinstance(item, dict) else ""
    if name_ar:
        return transliterate_arabic(name_ar)
    return ""


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
    reprint: bool = False,
    settings: dict = None,
):
    """Render the always-Arabic receipt body to a 1-bit PIL image (RTL).

    When ``proforma`` (F-059) the header reads *فاتورة مبدئية* instead of *فاتورة
    ضريبية* so the non-fiscal check the customer reviews before paying is never
    mistaken for a tax invoice.

    When ``reprint`` (ISSUE-075) the body carries a centered *نسخة — إعادة طباعة*
    stamp under the document header so a reprinted past sale is visibly a copy and
    never confused with the original tax invoice. Everything else — template,
    totals, the canonical ZATCA QR — is re-rendered unchanged from the stored sale.

    H26: ``settings`` carries the merchant's template knobs (font scale, custom
    header line, logo toggle). The seller name is always printed — it is fiscally
    required — but ``show_logo`` selects whether it is rendered as the prominent
    title (the textual brand mark) or in the normal body size; ``header_text``
    adds a custom centered line below it; ``font_scale`` scales every font.
    """
    from PIL import Image, ImageDraw, ImageFont

    settings = settings or _template_settings(None)
    scale = settings["font_scale"]
    width = settings["width_px"]
    # On a narrow 58mm head every font scales down with the paper so the same
    # content still fits across the 384-dot width without clipping (ISSUE-046).
    paper_scale = width / _WIDTH_PX
    scale = scale * paper_scale
    f_title = ImageFont.truetype(_FONT_PATH, int(40 * scale))
    f_big = ImageFont.truetype(_FONT_PATH, int(30 * scale))
    f_norm = ImageFont.truetype(_FONT_PATH, int(26 * scale))
    f_small = ImageFont.truetype(_FONT_PATH, int(24 * scale))

    margin = 12
    # Generous canvas; cropped to the rendered height before emitting. Scaled by
    # the font multiplier (taller fonts need a taller canvas) plus headroom for
    # an optional custom header line.
    est_h = int((640 + len(line_items or []) * 150) * max(scale, 1.0)) + 120
    img = Image.new("1", (width, est_h), 1)  # 1 == white background
    draw = ImageDraw.Draw(img)
    y = margin

    def row_h(font, pad: int = 8) -> int:
        ascent, descent = font.getmetrics()
        return ascent + descent + pad

    def center(text, font) -> None:
        nonlocal y
        t = _shape(text)
        w = _mixed_width(draw, t, font)
        _draw_mixed(draw, ((width - w) / 2, y), t, font, 0)
        y += row_h(font)

    def right(text, font) -> None:
        nonlocal y
        t = _shape(text)
        w = _mixed_width(draw, t, font)
        _draw_mixed(draw, (width - margin - w, y), t, font, 0)
        y += row_h(font)

    def lr(right_text, left_text, font) -> None:
        # Arabic label on the right (RTL), the code/amount on the left. The label
        # may carry the Riyal sign, so it goes through the mixed-font drawer.
        nonlocal y
        rt = _shape(right_text)
        rw = _mixed_width(draw, rt, font)
        _draw_mixed(draw, (width - margin - rw, y), rt, font, 0)
        _draw_mixed(draw, (margin, y), str(left_text), font, 0)
        y += row_h(font)

    def rule() -> None:
        nonlocal y
        y += 2
        draw.line([(margin, y), (width - margin, y)], fill=0, width=2)
        y += 12

    # ---- header ----
    # show_logo selects the prominence of the (always-present, fiscally-required)
    # seller name; header_text is the merchant's custom line printed beneath it.
    center(seller_name or _L["store"], f_title if settings["show_logo"] else f_norm)
    if settings["header_text"]:
        center(settings["header_text"], f_norm)
    lr(_L["vat_no"], vat_number or "-", f_small)
    center(_L["proforma"] if proforma else _L["tax_invoice"], f_big)
    # ISSUE-075: stamp a reprinted past sale as a duplicate copy so it can never
    # be mistaken for the original tax invoice.
    if reprint:
        center(_L["reprint"], f_norm)
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
    # ARC-07: the merchant template can hide the itemized VAT line (show_vat_details).
    if settings["show_vat_details"]:
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

    return img.crop((0, 0, width, min(y + margin, est_h)))


def _render_footer_image(settings: dict = None):
    """Render the always-Arabic footer to a 1-bit PIL image.

    H26: when the merchant's template carries ``footer_text`` it is printed (in
    place of the default *شكراً لزيارتكم*); otherwise the default thanks line is
    used. ``font_scale`` scales the footer to match the body.
    """
    from PIL import Image, ImageDraw, ImageFont

    settings = settings or _template_settings(None)
    width = settings["width_px"]
    text = settings["footer_text"] or _L["thanks"]
    font = ImageFont.truetype(_FONT_PATH, int(26 * settings["font_scale"] * (width / _WIDTH_PX)))
    ascent, descent = font.getmetrics()
    h = ascent + descent + 16
    img = Image.new("1", (width, h), 1)
    draw = ImageDraw.Draw(img)
    t = _shape(text)
    w = draw.textlength(t, font=font)
    draw.text(((width - w) / 2, 8), t, font=font, fill=0)
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
    reprint: bool = False,
    width: int,
    settings: dict = None,
) -> None:  # pragma: no cover - only hit in a degraded environment
    """Degraded ASCII receipt body when Arabic rendering is unavailable.

    Keeps the stream valid (OPS-08) so a printer still produces a receipt with the
    scannable ZATCA QR even if the font/shaping libraries are missing at runtime.
    H26: the merchant's custom header line is honored here too.
    """
    settings = settings or _template_settings(None)
    b.align("center").bold(True).double_size(True)
    b.line(seller_name or "Store")
    b.double_size(False)
    if settings["header_text"]:
        b.line(settings["header_text"])
    b.line("PROFORMA" if proforma else "TAX INVOICE")
    if reprint:
        b.line("REPRINT - COPY")
    b.line(f"VAT: {vat_number or '-'}")
    b.bold(False)
    b.line("-" * width)
    b.align("left")
    b.line(f"No: {invoice_number}")
    b.line(f"Date: {issue_date}")
    b.line("-" * width)
    for item in line_items or []:
        # CP437 can't render Arabic; romanize / fall back to the Latin name (FIS-03).
        name = _latin_display_name(item)[: width - 12]
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
    if settings["show_vat_details"]:
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
    reprint: bool = False,
    width: int = 42,
    open_drawer: bool = False,
    template: dict = None,
) -> bytes:
    """Render a transaction as an ESC/POS byte stream for an 80mm printer.

    The body is the always-Arabic raster receipt (SRS L10N-06 / PRN-01). When
    ``open_drawer`` is true (a cash sale) the stream carries a cash-drawer kick
    pulse (HW-04) so a connected till opens as the receipt prints.

    When ``proforma`` (F-059) the body is headed *فاتورة مبدئية* and **no QR is
    emitted regardless of ``zatca_qr``** — a check is non-fiscal and must carry no
    QR and no stamp, so it can never be mistaken for a tax invoice.

    H26: ``template`` is the merchant's default receipt template (a plain dict of
    knobs, or ``None`` for the defaults). It controls the custom header/footer
    lines, the logo-title prominence, the font scale, and — crucially — whether
    the ZATCA QR is emitted (``show_qr_code``). The always-Arabic fiscal invariant
    is unaffected: every label and the body still render in Arabic regardless.
    """
    b = EscPosBuilder()
    settings = _template_settings(template)

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
                reprint=reprint,
                settings=settings,
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
            reprint=reprint,
            width=settings["text_width"],
            settings=settings,
        )

    # A proforma is non-fiscal: never emit a QR even if one was passed (F-059).
    # H26: the merchant's template can also turn the QR off (show_qr_code).
    if zatca_qr and not proforma and settings["show_qr_code"]:
        b.align("center").qr(zatca_qr)

    # Footer (always Arabic when rendering is available).
    if rendered:
        try:
            b.align("center").raster_image(_render_footer_image(settings))
        except Exception:
            logger.warning("Footer render failed; using text fallback", exc_info=True)
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
    settings: dict = None,
):
    """Render an always-Arabic KOT body to a 1-bit PIL image (RTL) — F-057.

    Items are grouped under their course heading; each item shows only its
    quantity, name, modifier choices and any note — **never a price** (a kitchen
    ticket carries no money). ``courses`` is a list of
    ``{"course": str, "items": [{"name"/"name_ar", "qty", "notes", "modifiers": [str]}]}``.

    H26: ``settings`` carries the merchant's template knobs — the font scale and
    an optional custom header line apply to the kitchen ticket too (no QR, no
    footer, no prices ever).
    """
    from PIL import Image, ImageDraw, ImageFont

    settings = settings or _template_settings(None)
    width = settings["width_px"]
    # Scale the ticket fonts down with a narrow 58mm head so courses/modifiers
    # still fit across the 384-dot width without clipping (ISSUE-046).
    scale = settings["font_scale"] * (width / _WIDTH_PX)
    f_title = ImageFont.truetype(_FONT_PATH, int(42 * scale))
    f_course = ImageFont.truetype(_FONT_PATH, int(32 * scale))
    f_item = ImageFont.truetype(_FONT_PATH, int(34 * scale))
    f_small = ImageFont.truetype(_FONT_PATH, int(24 * scale))

    margin = 12
    n_items = sum(len(c.get("items") or []) for c in courses or [])
    est_h = int((360 + len(courses or []) * 60 + n_items * 130) * max(scale, 1.0)) + 120
    img = Image.new("1", (width, est_h), 1)
    draw = ImageDraw.Draw(img)
    y = margin

    def row_h(font, pad: int = 8) -> int:
        ascent, descent = font.getmetrics()
        return ascent + descent + pad

    def center(text, font) -> None:
        nonlocal y
        t = _shape(text)
        w = draw.textlength(t, font=font)
        draw.text(((width - w) / 2, y), t, font=font, fill=0)
        y += row_h(font)

    def right(text, font, indent: int = 0) -> None:
        nonlocal y
        t = _shape(text)
        w = draw.textlength(t, font=font)
        draw.text((width - margin - indent - w, y), t, font=font, fill=0)
        y += row_h(font)

    def lr(right_text, left_text, font) -> None:
        nonlocal y
        rt = _shape(right_text)
        rw = draw.textlength(rt, font=font)
        draw.text((width - margin - rw, y), rt, font=font, fill=0)
        draw.text((margin, y), str(left_text), font=font, fill=0)
        y += row_h(font)

    def rule() -> None:
        nonlocal y
        y += 2
        draw.line([(margin, y), (width - margin, y)], fill=0, width=2)
        y += 12

    # ---- header ----
    center(_L["kot"], f_title)
    center(station_name or _L["station"], f_course)
    if settings["header_text"]:
        center(settings["header_text"], f_small)
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

    return img.crop((0, 0, width, min(y + margin, est_h)))


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
    template: dict = None,
) -> bytes:
    """Render a per-station Kitchen Order Ticket as an ESC/POS byte stream (F-057).

    The KOT is an **always-Arabic** operational ticket (the fiscal-document Arabic
    invariant applies to every printable): items are grouped under each course and
    carry **no prices** — a kitchen ticket never shows money. No QR, no stamp.

    H26: ``template`` (the merchant's default receipt template, or ``None``)
    contributes the font scale and an optional custom header line.
    """
    b = EscPosBuilder()
    settings = _template_settings(template)
    rendered = False
    if _arabic_render_available():
        try:
            body = _render_kot_image(
                station_name=station_name,
                order_ref=order_ref,
                table_label=table_label,
                fired_at=fired_at,
                courses=courses,
                settings=settings,
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
            width=settings["text_width"],
        )

    b.feed(3).cut()
    return b.build()


def build_kot_base64(**kwargs) -> str:
    """Convenience wrapper returning the KOT as a base64 string."""
    return base64.b64encode(build_kot(**kwargs)).decode("ascii")
