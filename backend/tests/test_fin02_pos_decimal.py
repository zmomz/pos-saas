"""FIN-02 — Decimal VAT/totals in POS.

POS subtotal/discount/VAT/total used IEEE-754 ``float`` with ``round()`` and an
epsilon-based tender reconciliation. That drifts on the classic half-up boundary
(``round(0.015, 2) == 0.01``) and the epsilon let a penny-short split tender slip
through. These tests pin the POS math to ``core.money`` (FIN-01): penny-exact
totals, a QR TLV that carries the computed VAT, and exact tender reconciliation.
"""
from conftest import add_product, auth_headers, make_client_account
from services import zatca


async def _sale(client, headers, pid, *, price, qty=1, payments=None):
    payload = {
        "items": [{"product_id": pid, "name": "Item", "price": price, "quantity": qty}],
        "payment_method": "cash",
    }
    if payments is not None:
        payload["payments"] = payments
    return await client.post("/api/v1/pos/transaction", json=payload, headers=headers)


async def test_vat_and_total_are_penny_exact_half_up(client):
    """A 0.10 line VATs at 0.10*0.15 = 0.015 -> half-up 0.02, total 0.12.

    Float ``round(0.015, 2)`` yields 0.01 (total 0.11); Decimal half-up is 0.02.
    """
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Item", quantity=10, price=0.10)

    resp = await _sale(client, headers, pid, price=0.10, qty=1)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["subtotal"] == 0.10
    assert body["vat_amount"] == 0.02
    assert body["total_amount"] == 0.12


async def test_qr_tlv_vat_matches_computed_vat(client):
    """The stamped QR's VAT tag (5) carries the penny-exact computed VAT."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Item", quantity=10, price=0.10)

    resp = await _sale(client, headers, pid, price=0.10, qty=1)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["zatca_status"] == "signed"

    tags = zatca.parse_tlv_tags(body["zatca_qr"])
    # Tag 5 = VAT total; tag 4 = total with VAT — both the corrected Decimal values.
    assert tags[5].decode() == "0.02"
    assert tags[5].decode() == f"{body['vat_amount']:.2f}"
    assert tags[4].decode() == f"{body['total_amount']:.2f}"


async def test_split_tender_one_penny_short_is_rejected(client):
    """Exact reconciliation: a penny-short split tender is rejected (no epsilon)."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Item", quantity=10, price=10.0)

    # 10.00 + 15% VAT = 11.50 due; pay 11.49 (a penny short) across two legs.
    resp = await _sale(
        client, headers, pid, price=10.0, qty=1,
        payments=[{"method": "cash", "amount": 5.49}, {"method": "card", "amount": 6.00}],
    )
    assert resp.status_code == 400, resp.text
    assert "does not match" in resp.json()["detail"]


async def test_split_tender_exact_is_accepted(client):
    """The same total paid to the penny reconciles cleanly."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Item", quantity=10, price=10.0)

    resp = await _sale(
        client, headers, pid, price=10.0, qty=1,
        payments=[{"method": "cash", "amount": 5.50}, {"method": "card", "amount": 6.00}],
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["total_amount"] == 11.50
