"""Phase 6 (deferred): Arabic-glyph PDF rendering.

The invoice PDF now embeds the bundled Amiri OFL font and shapes/reorders Arabic
text, so the always-Arabic layout renders real Arabic glyphs (not transliterated
Latin). Falls back safely if the font/libs are unavailable.
"""
from services import pdf_render


def _render():
    return pdf_render.invoice_pdf_bytes(
        seller_name="متجر الاختبار",
        seller_vat="300000000000003",
        buyer_name="عميل نقدي",
        invoice_number="INV-0001-000001",
        issue_date="2026-06-03",
        line_items=[{"name": "قهوة عربية", "quantity": 2, "price": 12.5}],
        subtotal=25.0,
        discount=0.0,
        vat_amount=3.75,
        total_amount=28.75,
        qr_png_base64=None,
    )


def test_arabic_shaping_available():
    assert pdf_render._arabic_available() is True


def test_pdf_is_valid_and_embeds_arabic_font():
    data = _render()
    assert data[:5] == b"%PDF-"  # valid PDF magic
    assert len(data) > 1000
    # When the Amiri TTF is embedded, its name appears in the font descriptor.
    assert b"Amiri" in data


def test_shape_reorders_arabic():
    # Reshaping changes the code points (isolated -> contextual forms), so the
    # shaped output differs from the raw input for a multi-letter Arabic word.
    raw = "فاتورة"
    shaped = pdf_render._shape(raw)
    assert shaped != raw
    assert len(shaped) >= 1
