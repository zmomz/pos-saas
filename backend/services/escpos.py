"""ESC/POS thermal receipt builder (Phase E).

Generates a raw ESC/POS byte stream for an 80mm thermal printer: printer init,
centered header, the line items + totals, an embedded ZATCA QR code (the same
TLV base64 carried on the on-screen invoice), a feed and a partial cut. The
bytes are returned base64-encoded so the browser frontend can stream them to a
WebUSB / Web Bluetooth printer (see `frontend/src/lib/thermalPrint.ts`).

Note on Arabic: ESC/POS glyph rendering for Arabic depends on the printer's
installed code page. Label text here is ASCII/transliterated so it prints on any
device; for native Arabic glyphs the receipt is the always-Arabic HTML invoice
(`GET /pos/transactions/{id}/invoice`) rendered to the customer/printer driver.
Identifiers and amounts (the legally relevant fields) print identically either
way, and the embedded QR is the canonical ZATCA payload.
"""
import base64

ESC = 0x1B
GS = 0x1D


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

    def build(self) -> bytes:
        return bytes(self._buf)


def _money(value: float) -> str:
    return f"{value or 0:.2f}"


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
    zatca_qr: str,
    width: int = 42,
    open_drawer: bool = False,
) -> bytes:
    """Render a transaction as an ESC/POS byte stream for an 80mm printer.

    When ``open_drawer`` is true (a cash sale) the stream carries a cash-drawer
    kick pulse (HW-04) so a connected till opens as the receipt prints.
    """
    b = EscPosBuilder()

    if open_drawer:
        # Pulse the drawer first so the till opens for the cashier immediately.
        b.kick_drawer()

    b.align("center").bold(True).double_size(True)
    b.line(seller_name or "Store")
    b.double_size(False)
    b.line(f"VAT: {vat_number or '-'}")
    b.bold(False)
    b.line("Tax Invoice / فاتورة ضريبية")
    b.line("-" * width)

    b.align("left")
    b.line(f"Invoice: {invoice_number}")
    b.line(f"Date:    {issue_date}")
    b.line("-" * width)

    for item in line_items or []:
        name = str(item.get("name", "")) [: width - 12]
        qty = item.get("quantity", 1)
        price = float(item.get("price", 0) or 0)
        item_disc = float(item.get("discount", 0) or 0)
        amount = price * qty - item_disc
        b.line(name)
        right = f"{qty} x {_money(price)} = {_money(amount)}"
        b.line(right.rjust(width))

    b.line("-" * width)
    b.line(f"Subtotal:".ljust(width - 12) + _money(subtotal).rjust(12))
    if discount:
        b.line(f"Discount:".ljust(width - 12) + ("-" + _money(discount)).rjust(12))
    b.line(f"VAT:".ljust(width - 12) + _money(vat_amount).rjust(12))
    b.bold(True)
    b.line(f"TOTAL (SAR):".ljust(width - 12) + _money(total_amount).rjust(12))
    b.bold(False)
    b.line("-" * width)

    if zatca_qr:
        b.align("center").qr(zatca_qr)
    b.align("center").feed(1).line("Thank you / شكرا لزيارتكم")
    b.feed(3).cut()
    return b.build()


def build_receipt_base64(**kwargs) -> str:
    """Convenience wrapper returning the receipt as a base64 string."""
    return base64.b64encode(build_receipt(**kwargs)).decode("ascii")
