"""ARC-07 — the persisted ``show_vat_details`` template knob must drive output.

The merchant template carried a ``show_vat_details`` boolean that was saved but
never read: ``escpos`` always printed the itemized VAT line regardless. A
persisted toggle that is a no-op is a bug. These tests pin the knob to the
rendered byte stream — default on (historical behaviour), and suppressing the
standalone VAT line when turned off — while keeping the always-Arabic fiscal
invariant (the ZATCA QR, which carries the tax amount, is untouched).
"""
import base64

import pytest

from conftest import auth_headers, make_client_account
from services.escpos import build_receipt

# GS ( k — the QR-code command family (present only when a QR is emitted).
QR_CMD = bytes([0x1D, 0x28, 0x6B])
# GS v 0 — raster bit-image (the always-Arabic body).
RASTER_CMD = bytes([0x1D, 0x76, 0x30])


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


def test_show_vat_details_false_suppresses_vat_line():
    """Turning show_vat_details off drops the itemized VAT row, shrinking the
    raster relative to the default (where the row prints) (AC1/AC2)."""
    with_vat = _sample(template={"show_vat_details": True})
    without_vat = _sample(template={"show_vat_details": False})
    assert with_vat != without_vat, "show_vat_details must change the rendered bytes"
    # The VAT row is one fewer line of raster when suppressed => fewer bitmap bytes.
    assert len(with_vat) > len(without_vat)


def test_default_keeps_vat_line():
    """Absent a template — or with the field null — the VAT line still prints, so
    the historical fiscal receipt is unchanged (AC2)."""
    default = _sample(template=None)
    null_field = _sample(template={"show_vat_details": None})
    on = _sample(template={"show_vat_details": True})
    assert len(default) == len(on), "no template defaults to show_vat_details on"
    assert len(null_field) == len(on), "a null field defaults to show_vat_details on"


def test_suppressing_vat_keeps_qr_and_arabic():
    """Hiding the itemized VAT line never strips the ZATCA QR (which carries the
    tax amount) or breaks the always-Arabic raster invariant (AC3)."""
    data = _sample(template={"show_vat_details": False})
    assert QR_CMD in data, "the ZATCA QR must still print"
    assert RASTER_CMD in data, "the body must remain an Arabic raster"


@pytest.mark.asyncio
async def test_default_template_drives_vat_suppression_endpoint(client):
    """End-to-end: a saved default template with show_vat_details=False renders a
    shorter receipt than the default through the real /escpos endpoint, proving
    the knob loads at print time (AC1/AC2)."""
    user, token, client_id = await make_client_account(client)
    from conftest import add_product

    async def _sale():
        pid = await add_product(client_id, user["id"], quantity=10, price=10.0)
        resp = await client.post(
            "/api/v1/pos/transaction",
            headers=auth_headers(token),
            json={
                "items": [{"product_id": pid, "name": "Widget", "price": 10.0, "quantity": 1}],
                "payment_method": "cash",
            },
        )
        return resp.json()["id"]

    async def _escpos(txn_id):
        resp = await client.get(
            f"/api/v1/pos/transactions/{txn_id}/escpos", headers=auth_headers(token)
        )
        assert resp.status_code == 200, resp.text
        return base64.b64decode(resp.json()["data"])

    # Baseline: no template -> VAT line prints.
    baseline = await _escpos(await _sale())

    # Save a default template that hides the itemized VAT line.
    tpl = await client.post(
        "/api/v1/entities/receipt_templates",
        headers=auth_headers(token),
        json={"name": "Default", "is_default": True, "show_vat_details": False},
    )
    assert tpl.status_code == 201, tpl.text

    hidden = await _escpos(await _sale())
    assert RASTER_CMD in hidden, "body still renders as Arabic raster"
    assert len(hidden) < len(baseline), "show_vat_details=False must shorten the receipt"
