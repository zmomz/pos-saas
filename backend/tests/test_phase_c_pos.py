"""Phase C — payment breakdown, Arabic invoice document, email receipt, low-stock."""
from conftest import add_product, auth_headers, make_client_account


async def _make_sale(client, headers, pid, qty=1, price=100.0, payments=None):
    payload = {
        "items": [{"product_id": pid, "name": "Item", "price": price, "quantity": qty}],
        "payment_method": "cash",
    }
    if payments is not None:
        payload["payments"] = payments
    return await client.post("/api/v1/pos/transaction", json=payload, headers=headers)


async def test_payment_breakdown_split_ok(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Item", quantity=10, price=100.0)

    # 100 + 15% VAT = 115 total; split cash 15 + card 100.
    resp = await _make_sale(
        client, headers, pid,
        payments=[{"method": "cash", "amount": 15.0}, {"method": "card", "amount": 100.0}],
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_amount"] == 115.0
    assert body["payment_method"] == "mixed"
    assert body["payment_breakdown"] is not None
    assert '"card"' in body["payment_breakdown"]


async def test_payment_breakdown_mismatch_rejected(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Item", quantity=10, price=100.0)

    resp = await _make_sale(
        client, headers, pid,
        payments=[{"method": "cash", "amount": 50.0}],  # short of the 115 total
    )
    assert resp.status_code == 400


async def test_invoice_document_is_always_arabic(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Item", quantity=10, price=100.0)
    sale = await _make_sale(client, headers, pid)
    txn_id = sale.json()["id"]
    invoice_number = sale.json()["invoice_number"]

    doc = await client.get(f"/api/v1/pos/transactions/{txn_id}/invoice", headers=headers)
    assert doc.status_code == 200, doc.text
    html = doc.text
    assert 'dir="rtl"' in html and 'lang="ar"' in html
    assert "فاتورة ضريبية" in html  # "Tax Invoice" in Arabic
    assert invoice_number in html


async def test_email_receipt_enabled_by_default(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Item", quantity=10, price=100.0)
    sale = await _make_sale(client, headers, pid)
    txn_id = sale.json()["id"]

    resp = await client.post(
        f"/api/v1/pos/transactions/{txn_id}/email",
        json={"to_email": "buyer@example.com"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "queued"


async def test_sale_below_threshold_still_succeeds(client):
    # Selling stock down to/below the low-stock threshold must not break the sale
    # (the alert dispatch is best-effort and post-commit).
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Scarce", quantity=11, price=1.0)
    resp = await _make_sale(client, headers, pid, qty=5, price=1.0)
    assert resp.status_code == 200, resp.text
