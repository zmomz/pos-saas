"""Phase E — ESC/POS thermal receipt byte stream.

F-021 (PRN-01 / L10N-06): the thermal receipt is the most-printed fiscal
document and must render in **Arabic, RTL, Arabic-Indic digits** regardless of UI
language. The body is emitted as a raster bit-image (GS v 0) rendered from the
bundled Amiri font, so these tests assert the raster command is present and the
old English/transliterated ASCII labels are gone — rather than asserting ASCII
text that would mean the receipt was still English.
"""
import base64

import pytest

from conftest import add_product, auth_headers, make_client_account
from services.escpos import _item_display_name, build_receipt

# GS v 0 — raster bit-image command (the Arabic receipt body is drawn as a bitmap).
RASTER_CMD = bytes([0x1D, 0x76, 0x30])
# English/transliterated labels that must NOT appear (the F-021 regression).
ENGLISH_LABELS = [b"Invoice:", b"Subtotal:", b"TOTAL (SAR):", b"VAT:", b"Tax Invoice"]


def _sample_receipt(**overrides) -> bytes:
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


def test_build_receipt_structure():
    data = _sample_receipt()
    # Starts with ESC @ initialise.
    assert data[:2] == bytes([0x1B, 0x40])
    # Contains a QR command and a partial cut.
    assert bytes([0x1D, 0x28, 0x6B]) in data  # GS ( k  (QR family)
    assert bytes([0x1D, 0x56, 66, 0]) in data  # GS V 66 0 (partial cut)


def test_thermal_receipt_is_arabic_raster_not_english_ascii():
    """The F-021 catch-forever: the receipt body is an Arabic raster, not English."""
    data = _sample_receipt()
    # The always-Arabic body is emitted as a raster bit-image.
    assert RASTER_CMD in data, "receipt body must be rendered as an Arabic raster image"
    # None of the old English/transliterated labels survive.
    for label in ENGLISH_LABELS:
        assert label not in data, f"English label {label!r} must not appear on the Arabic receipt"


def test_thermal_receipt_prefers_name_ar():
    """The Arabic line name is used when present, else the default name (PRN-01)."""
    assert _item_display_name({"name": "Widget", "name_ar": "أداة"}) == "أداة"
    assert _item_display_name({"name": "Widget", "name_ar": "  "}) == "Widget"
    assert _item_display_name({"name": "Widget"}) == "Widget"


@pytest.mark.asyncio
async def test_escpos_endpoint(client):
    user, token, client_id = await make_client_account(client)
    pid = await add_product(client_id, user["id"], quantity=10, price=10.0)
    sale = await client.post(
        "/api/v1/pos/transaction",
        headers=auth_headers(token),
        json={
            "items": [{"product_id": pid, "name": "Widget", "price": 10.0, "quantity": 1}],
            "payment_method": "cash",
        },
    )
    txn_id = sale.json()["id"]

    resp = await client.get(
        f"/api/v1/pos/transactions/{txn_id}/escpos", headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["format"] == "escpos"
    assert body["invoice_number"]  # carried as JSON metadata for the frontend
    raw = base64.b64decode(body["data"])
    assert raw[:2] == bytes([0x1B, 0x40])
    # Always-Arabic raster body; no English labels leak through.
    assert RASTER_CMD in raw
    for label in ENGLISH_LABELS:
        assert label not in raw


@pytest.mark.asyncio
async def test_escpos_other_client_404(client):
    user_a, token_a, cid_a = await make_client_account(client)
    pid = await add_product(cid_a, user_a["id"], quantity=10, price=10.0)
    sale = await client.post(
        "/api/v1/pos/transaction",
        headers=auth_headers(token_a),
        json={
            "items": [{"product_id": pid, "name": "W", "price": 10.0, "quantity": 1}],
            "payment_method": "cash",
        },
    )
    txn_id = sale.json()["id"]

    _, token_b, _ = await make_client_account(client)
    resp = await client.get(
        f"/api/v1/pos/transactions/{txn_id}/escpos", headers=auth_headers(token_b)
    )
    assert resp.status_code == 404
