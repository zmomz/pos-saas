"""ISSUE-046 — 58mm receipt paper support.

H26 follow-up: the raster body was hardcoded to an 80mm head (576 dots). A
narrow 58mm thermal printer has a 384-dot printable width, so an 80mm-wide
bitmap is clipped on the right. These tests assert the merchant template's
``paper_size`` knob drives the rendered raster width for both the receipt and
the KOT — and that 80mm remains the unchanged default.

The raster bit-image command is ``GS v 0 m xL xH yL yH [data]``; the image width
in *bytes* is ``xL + xH*256`` (so the width in dots is that times eight). We read
the width straight out of the emitted stream — the public, on-the-wire contract.
"""
import base64

import pytest

from conftest import auth_headers, make_client_account
from services.escpos import build_receipt, build_kot

# GS v 0 — raster bit-image (the always-Arabic body / footer / KOT).
RASTER_CMD = bytes([0x1D, 0x76, 0x30])

WIDTH_80MM = 576  # dots — the historical default
WIDTH_58MM = 384  # dots — a 58mm head's printable area


def _raster_widths(stream: bytes) -> list:
    """Every raster bit-image's width (in dots) emitted in the stream, in order."""
    widths = []
    idx = stream.find(RASTER_CMD)
    while idx != -1:
        # ...CMD(3) m(1) xL xH ...  -> bytes-per-row = xL + xH*256
        bytes_per_row = stream[idx + 4] + (stream[idx + 5] << 8)
        widths.append(bytes_per_row * 8)
        idx = stream.find(RASTER_CMD, idx + 3)
    return widths


def _sample(**overrides) -> bytes:
    kwargs = dict(
        seller_name="Test Shop",
        vat_number="300000000000003",
        invoice_number="INV-0001-000001",
        issue_date="2026-06-02 10:00",
        line_items=[{"name": "Widget", "name_ar": "أداة", "price": 10.0, "quantity": 2, "discount": 0}],
        subtotal=20.0,
        discount=0.0,
        vat_amount=3.0,
        total_amount=23.0,
        zatca_qr="AQVTdG9yZQ==",
    )
    kwargs.update(overrides)
    return build_receipt(**kwargs)


def test_58mm_receipt_renders_at_narrow_width():
    """A 58mm template lays the receipt body out at 384 dots, not 576 (AC1)."""
    data = _sample(template={"paper_size": "58mm"})
    widths = _raster_widths(data)
    assert widths, "the receipt must still emit an Arabic raster body"
    assert all(w == WIDTH_58MM for w in widths), (
        f"every raster (body + footer) must be 384 dots wide for 58mm, got {widths}"
    )


def test_80mm_remains_the_unchanged_default():
    """No template — and an explicit 80mm — both render at the historical 576
    dots, so existing 80mm printers are untouched (AC2)."""
    default_widths = _raster_widths(_sample(template=None))
    explicit_widths = _raster_widths(_sample(template={"paper_size": "80mm"}))
    assert default_widths, "the receipt must emit an Arabic raster body"
    assert all(w == WIDTH_80MM for w in default_widths), default_widths
    assert all(w == WIDTH_80MM for w in explicit_widths), explicit_widths


def test_unknown_paper_size_falls_back_to_80mm():
    """A size that never reaches the thermal path (e.g. A4) defaults to 80mm so
    the renderer can't produce a degenerate width (AC2)."""
    widths = _raster_widths(_sample(template={"paper_size": "A4"}))
    assert all(w == WIDTH_80MM for w in widths), widths


def _sample_kot(**overrides) -> bytes:
    kwargs = dict(
        station_name="المطبخ",
        order_ref="12",
        table_label="5",
        fired_at="2026-06-02 10:00",
        courses=[
            {
                "course": "المقبلات",
                "items": [
                    {"name": "Soup", "name_ar": "شوربة", "qty": 2, "modifiers": ["بدون ملح"]},
                ],
            }
        ],
    )
    kwargs.update(overrides)
    return build_kot(**kwargs)


def test_58mm_kot_renders_at_narrow_width():
    """The kitchen ticket honors 58mm too — 384-dot raster, not 576 (AC1)."""
    narrow = _raster_widths(_sample_kot(template={"paper_size": "58mm"}))
    wide = _raster_widths(_sample_kot(template={"paper_size": "80mm"}))
    assert narrow and all(w == WIDTH_58MM for w in narrow), narrow
    assert wide and all(w == WIDTH_80MM for w in wide), wide


def _ink_bbox(img):
    """Bounding box of the *black* ink on a mode-"1" receipt image.

    In mode "1" white is 1 and black (ink) is 0, so ``getbbox`` would return the
    box of the white background. Invert first so the box bounds the ink.
    """
    inverted = img.point(lambda p: 0 if p else 255)
    return inverted.getbbox()


def test_58mm_receipt_has_no_horizontal_overflow():
    """Even a long seller name fits inside the 384-dot canvas with no ink spilling
    past either edge — i.e. nothing is clipped on a 58mm head (AC1)."""
    from services.escpos import _render_receipt_image, _template_settings

    settings = _template_settings({"paper_size": "58mm"})
    img = _render_receipt_image(
        seller_name="مطعم ومقهى الذواقة الفاخر للمأكولات الشرقية والعالمية",
        vat_number="300000000000003",
        invoice_number="INV-0001-000001",
        issue_date="2026-06-02 10:00",
        line_items=[{"name": "Widget", "name_ar": "أداة فاخرة جداً", "price": 1234.56, "quantity": 9, "discount": 0}],
        subtotal=11111.04,
        discount=0.0,
        vat_amount=1666.66,
        total_amount=12777.70,
        settings=settings,
    )
    assert img.size[0] == WIDTH_58MM
    bbox = _ink_bbox(img)
    assert bbox is not None, "the receipt must have drawn some ink"
    left, _, right, _ = bbox
    assert left >= 0, f"ink overflows the left edge (x={left})"
    assert right <= WIDTH_58MM, f"ink overflows the right edge (x={right} > {WIDTH_58MM})"


async def _make_sale(client, token, client_id, user_id):
    from conftest import add_product

    pid = await add_product(client_id, user_id, quantity=10, price=10.0)
    sale = await client.post(
        "/api/v1/pos/transaction",
        headers=auth_headers(token),
        json={
            "items": [{"product_id": pid, "name": "Widget", "price": 10.0, "quantity": 1}],
            "payment_method": "cash",
        },
    )
    return sale.json()["id"]


@pytest.mark.asyncio
async def test_saved_58mm_template_drives_escpos_endpoint(client):
    """End-to-end: a saved default template with paper_size=58mm renders the real
    /escpos receipt at 384 dots — proving the loader's paper_size knob reaches the
    renderer at print time (AC1)."""
    user, token, client_id = await make_client_account(client)
    tpl = await client.post(
        "/api/v1/entities/receipt_templates",
        headers=auth_headers(token),
        json={"name": "Narrow", "is_default": True, "paper_size": "58mm"},
    )
    assert tpl.status_code == 201, tpl.text

    txn_id = await _make_sale(client, token, client_id, user["id"])
    resp = await client.get(
        f"/api/v1/pos/transactions/{txn_id}/escpos", headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    raw = base64.b64decode(resp.json()["data"])
    widths = _raster_widths(raw)
    assert widths and all(w == WIDTH_58MM for w in widths), (
        f"the saved 58mm template must render the receipt at 384 dots, got {widths}"
    )
