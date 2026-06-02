"""Phase E — ESC/POS thermal receipt byte stream."""
import base64

import pytest

from conftest import add_product, auth_headers, make_client_account
from services.escpos import build_receipt


def test_build_receipt_structure():
    data = build_receipt(
        seller_name="Test Shop",
        vat_number="300000000000003",
        invoice_number="INV-0001-000001",
        issue_date="2026-06-02 10:00",
        line_items=[{"name": "Widget", "price": 10.0, "quantity": 2, "discount": 0}],
        subtotal=20.0,
        discount=0.0,
        vat_amount=3.0,
        total_amount=23.0,
        zatca_qr="AQVTdG9yZQ==",
    )
    # Starts with ESC @ initialise.
    assert data[:2] == bytes([0x1B, 0x40])
    # Contains the invoice number and a QR command and a partial cut.
    assert b"INV-0001-000001" in data
    assert bytes([0x1D, 0x28, 0x6B]) in data  # GS ( k  (QR family)
    assert bytes([0x1D, 0x56, 66, 0]) in data  # GS V 66 0 (partial cut)


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
    raw = base64.b64decode(body["data"])
    assert raw[:2] == bytes([0x1B, 0x40])
    assert body["invoice_number"].encode() in raw


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
