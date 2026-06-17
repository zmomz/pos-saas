"""Phase D — numerals in the always-Arabic invoice document.

Product decision (2026-06-18): Western numerals everywhere, including receipts —
overriding the old SRS L10N-03 "receipts always Arabic-Indic" rule. The Arabic
text/labels stay Arabic; only the digits and separators are Western now.
"""
from core.formatting import format_money_ar, to_arabic_digits
from conftest import add_product, auth_headers, make_client_account


def test_format_money_ar_uses_western_digits_and_separators():
    out = format_money_ar(1234.5)
    # Western grouped form, no Arabic-Indic digits or separators.
    assert out == "1,234.50"
    assert not any(c in out for c in "٠١٢٣٤٥٦٧٨٩")
    assert "٫" not in out  # no Arabic decimal separator
    assert "٬" not in out  # no Arabic thousands separator


def test_to_arabic_digits_passes_western_through_unchanged():
    # Back-compat shim: no longer converts to Arabic-Indic.
    assert to_arabic_digits("INV-2026-07") == "INV-2026-07"
    assert to_arabic_digits(123) == "123"


async def test_invoice_totals_render_in_western_digits(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Item", quantity=10, price=100.0)
    sale = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [
                {"product_id": pid, "name": "Item", "price": 100.0, "quantity": 1}
            ],
            "payment_method": "cash",
        },
        headers=headers,
    )
    txn_id = sale.json()["id"]
    invoice_number = sale.json()["invoice_number"]

    doc = await client.get(
        f"/api/v1/pos/transactions/{txn_id}/invoice", headers=headers
    )
    html = doc.text
    # Totals (e.g. 115.00) now read in Western numerals; no Arabic-Indic digits.
    assert format_money_ar(115.0) in html
    assert not any(c in html for c in "٠١٢٣٤٥٦٧٨٩")
    # The invoice number is an identifier/code and stays in Western digits.
    assert invoice_number in html
