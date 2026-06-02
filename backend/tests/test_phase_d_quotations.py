"""Phase D — quotations (عرض سعر) feature + always-Arabic quotation document."""
import json

from conftest import auth_headers, make_client_account, register_user, unique_email


async def _create_quote(client, headers, **overrides):
    payload = {
        "customer_name": "Acme Co",
        "items_json": json.dumps(
            [{"name": "Widget", "quantity": 2, "price": 50.0}]
        ),
        "subtotal": 100.0,
        "vat_amount": 15.0,
        "total_amount": 115.0,
    }
    payload.update(overrides)
    return await client.post(
        "/api/v1/entities/quotations", json=payload, headers=headers
    )


async def test_create_quotation_autonumbers(client):
    _user, token, _cid = await make_client_account(client)
    headers = auth_headers(token)

    resp = await _create_quote(client, headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    # A quote number is auto-assigned when none is supplied.
    assert body["quote_number"]
    assert body["quote_number"].startswith("QT-")
    assert body["total_amount"] == 115.0


async def test_quotation_document_is_always_arabic_and_not_a_tax_invoice(client):
    _user, token, _cid = await make_client_account(client)
    headers = auth_headers(token)
    quote_id = (await _create_quote(client, headers)).json()["id"]

    doc = await client.get(
        f"/api/v1/entities/quotations/{quote_id}/document", headers=headers
    )
    assert doc.status_code == 200, doc.text
    html = doc.text
    # Forced RTL/Arabic regardless of UI language (SRS §7).
    assert 'dir="rtl"' in html and 'lang="ar"' in html
    assert "<h1>عرض سعر</h1>" in html  # titled "Price Quotation"
    # A quotation is NOT a fiscal document — it must not be titled as a tax
    # invoice (the disclaimer text *mentions* the phrase, the heading must not).
    assert "<h1>فاتورة ضريبية</h1>" not in html
    assert "عرض سعر وليس فاتورة ضريبية" in html
    # Arabic-Indic numerals in the totals (L10N-03): 115.00 -> ١١٥٫٠٠
    assert "١" in html


async def test_quotation_is_owner_scoped(client):
    _user_a, token_a, _cid = await make_client_account(client)
    quote_id = (await _create_quote(client, auth_headers(token_a))).json()["id"]

    # A different user cannot read or render someone else's quotation.
    _user_b, token_b, _ = await register_user(client, email=unique_email())
    headers_b = auth_headers(token_b)

    assert (
        await client.get(
            f"/api/v1/entities/quotations/{quote_id}", headers=headers_b
        )
    ).status_code == 404
    assert (
        await client.get(
            f"/api/v1/entities/quotations/{quote_id}/document", headers=headers_b
        )
    ).status_code == 404
