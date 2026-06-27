"""ARC-06 — pixel-identity characterization for the shared RTL layout helper.

The always-Arabic receipt body (``_render_receipt_image``) and the kitchen
ticket (``_render_kot_image``) historically each defined their own copy of the
same top-down RTL layout primitives (``row_h``/``center``/``right``/``lr``/
``rule``). ARC-06 extracts that duplicated block into ONE helper used by both
call-sites. This test pins the EXACT rendered bytes of both paths so the
extraction is proven to be behavior-preserving down to the pixel — the receipt
labels carry the Riyal glyph (mixed-font drawing) while the KOT never does, and
the helper must keep that distinction.
"""

import hashlib

from services import escpos as e

# Golden hashes captured from the pre-refactor implementation. If the extracted
# helper drifts the layout of either path by a single pixel, these assertions
# fail.
_RECEIPT_SHA = "c32a6fc56f5afa545c842a5a45b2bfedb6f60fb6681b0bc0f8f4b5b1e52c02a7"
_KOT_SHA = "27ad49acefdb51b65259ac5a8017702868166fc2de06bac1dc542d7fde4f6b59"


def _sha(img):
    return hashlib.sha256(img.tobytes()).hexdigest()


def test_receipt_render_pixel_identical():
    img = e._render_receipt_image(
        seller_name="متجر التجربة",
        vat_number="300000000000003",
        invoice_number="INV-1001",
        issue_date="2026-06-27 12:00",
        line_items=[
            {"name": "Latte", "name_ar": "لاتيه", "quantity": 2, "price": 15.0, "discount": 1.5},
            {"name": "Cake", "name_ar": "كيك", "quantity": 1, "price": 22.0},
        ],
        subtotal=52.0,
        discount=1.5,
        vat_amount=7.575,
        total_amount=58.075,
        tip_amount=5.0,
        service_charge=3.0,
        proforma=False,
        reprint=True,
    )
    assert img.size == (576, 1040)
    assert _sha(img) == _RECEIPT_SHA


def test_kot_render_pixel_identical():
    img = e._render_kot_image(
        station_name="المطبخ",
        order_ref="A-12",
        table_label="طاولة 4",
        fired_at="12:01",
        courses=[
            {
                "course": "المقبلات",
                "items": [
                    {"name": "Fries", "name_ar": "بطاطس", "qty": 2, "modifiers": ["حار"], "notes": "بدون ملح"},
                ],
            },
            {"course": "الرئيسية", "items": [{"name": "Burger", "name_ar": "برغر", "qty": 1}]},
        ],
    )
    assert img.size == (576, 751)
    assert _sha(img) == _KOT_SHA
