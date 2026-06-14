"""ISSUE-045 — receipt-template fields reach the ESC/POS renderer.

H26: `escpos.py` never loaded a template, so every one of the merchant's
template knobs (header/footer/logo/show_qr/font_size) was ignored at print
time. These tests assert that a template passed to `build_receipt`/`build_kot`
actually changes the rendered byte stream — and that the always-Arabic fiscal
invariant (F-021) still holds regardless.
"""
import base64

import pytest

from conftest import auth_headers, make_client_account
from services.escpos import build_receipt, build_kot

# GS ( k — the QR-code command family (present only when a QR is emitted).
QR_CMD = bytes([0x1D, 0x28, 0x6B])
# GS v 0 — raster bit-image (the always-Arabic body).
RASTER_CMD = bytes([0x1D, 0x76, 0x30])
ENGLISH_LABELS = [b"Invoice:", b"Subtotal:", b"TOTAL (SAR):", b"VAT:", b"Tax Invoice"]


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


def test_show_qr_code_false_suppresses_qr():
    """The template's show_qr_code knob gates the ZATCA QR (AC1/AC2)."""
    with_qr = _sample(template={"show_qr_code": True})
    without_qr = _sample(template={"show_qr_code": False})
    assert QR_CMD in with_qr, "QR must print when the template enables it"
    assert QR_CMD not in without_qr, "QR must be suppressed when the template disables it"


def test_no_template_keeps_default_behaviour():
    """Absent a template the receipt is unchanged: QR present, body Arabic (AC1)."""
    data = _sample(template=None)
    assert QR_CMD in data
    assert RASTER_CMD in data


def test_font_size_changes_rendered_output():
    """A larger font_size produces a visibly taller raster than a smaller one (AC2)."""
    small = _sample(template={"font_size": "small"})
    large = _sample(template={"font_size": "large"})
    assert small != large, "font_size must change the rendered bytes"
    # The raster is the bulk of the stream; a bigger font => more bitmap bytes.
    assert len(large) > len(small)


def test_header_text_changes_rendered_output():
    """A custom header line reaches the rendered output (AC2)."""
    plain = _sample(template={"header_text": ""})
    with_header = _sample(template={"header_text": "مرحباً بكم"})
    assert with_header != plain, "header_text must change the rendered bytes"
    assert len(with_header) > len(plain), "the extra header line lengthens the raster"


def test_footer_text_changes_rendered_output():
    """A custom footer line reaches the rendered output (AC2)."""
    default_footer = _sample(template=None)
    custom_footer = _sample(template={"footer_text": "نتمنى لكم يوماً سعيداً جداً"})
    assert custom_footer != default_footer, "footer_text must change the rendered bytes"


def test_show_logo_changes_title_prominence():
    """Toggling show_logo changes the rendered output (AC2)."""
    with_logo = _sample(template={"show_logo": True})
    without_logo = _sample(template={"show_logo": False})
    assert with_logo != without_logo, "show_logo must change the rendered bytes"


def test_template_preserves_arabic_invariant():
    """Even with a fully-populated template the body stays Arabic raster (AC3)."""
    data = _sample(
        template={
            "header_text": "متجر",
            "footer_text": "شكراً",
            "show_logo": False,
            "show_qr_code": True,
            "font_size": "large",
        }
    )
    assert RASTER_CMD in data, "body must remain an Arabic raster regardless of template"
    for label in ENGLISH_LABELS:
        assert label not in data, f"English label {label!r} must not leak onto the receipt"


def _sample_kot(**overrides) -> bytes:
    kwargs = dict(
        station_name="المطبخ",
        order_ref="12",
        table_label="5",
        fired_at="2026-06-02 10:00",
        courses=[{"course": "المقبلات", "items": [{"name": "Soup", "name_ar": "شوربة", "qty": 2}]}],
    )
    kwargs.update(overrides)
    return build_kot(**kwargs)


def test_kot_font_size_changes_output():
    """build_kot honors the template font scale and stays Arabic raster (AC1/AC3)."""
    small = _sample_kot(template={"font_size": "small"})
    large = _sample_kot(template={"font_size": "large"})
    assert small != large, "font_size must change the KOT bytes"
    assert len(large) > len(small)
    assert RASTER_CMD in large
    for label in [b"KOT", b"Station", b"Order:"]:
        assert label not in large, f"English KOT label {label!r} must not leak"


async def _make_sale(client, token, user_id, client_id):
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
async def test_default_template_drives_escpos_endpoint(client):
    """End-to-end: a saved default template with show_qr_code=False suppresses the
    QR on the real /escpos receipt — proving the renderer loads the merchant's
    template at print time (AC1/AC2)."""
    user, token, client_id = await make_client_account(client)

    # Save a default template that turns the ZATCA QR off.
    tpl = await client.post(
        "/api/v1/entities/receipt_templates",
        headers=auth_headers(token),
        json={"name": "Default", "is_default": True, "show_qr_code": False},
    )
    assert tpl.status_code == 201, tpl.text

    txn_id = await _make_sale(client, token, user["id"], client_id)
    resp = await client.get(
        f"/api/v1/pos/transactions/{txn_id}/escpos", headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    raw = base64.b64decode(resp.json()["data"])
    assert RASTER_CMD in raw, "body still renders as Arabic raster"
    assert QR_CMD not in raw, "the template's show_qr_code=False must suppress the QR"


@pytest.mark.asyncio
async def test_no_template_endpoint_keeps_qr(client):
    """Absent any template, the /escpos receipt keeps the QR (default behaviour)."""
    user, token, client_id = await make_client_account(client)
    txn_id = await _make_sale(client, token, user["id"], client_id)
    resp = await client.get(
        f"/api/v1/pos/transactions/{txn_id}/escpos", headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    raw = base64.b64decode(resp.json()["data"])
    assert QR_CMD in raw, "with no template the canonical ZATCA QR must still print"
