"""Phase D — Arabic-Indic numerals in the always-Arabic invoice document (L10N-03)."""
from core.formatting import format_money_ar, to_arabic_digits
from conftest import add_product, auth_headers, make_client_account


def test_format_money_ar_uses_arabic_digits_and_separators():
    out = format_money_ar(1234.5)
    # Western digits must be fully replaced.
    assert not any(c in out for c in "0123456789")
    assert "٫" in out  # Arabic decimal separator
    assert "٬" in out  # Arabic thousands separator
    assert out == "١٬٢٣٤٫٥٠"


def test_to_arabic_digits_leaves_letters_untouched():
    assert to_arabic_digits("INV-2026-07") == "INV-٢٠٢٦-٠٧"


async def test_invoice_totals_render_in_arabic_indic(client):
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
    # Totals (e.g. 115.00) now read in Arabic-Indic numerals.
    assert "١" in html
    assert format_money_ar(115.0) in html
    # The invoice number is an identifier/code and stays in Western digits so it
    # round-trips when typed back into a system.
    assert invoice_number in html
