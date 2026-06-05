"""Phase 7 — VAT / tax summary by rate (F-069 / RPT-05).

A merchant filing a ZATCA VAT return needs output VAT broken out into the return
boxes — standard-rated (15%) / zero-rated (0%) / exempt — each with its taxable
base and VAT amount, rather than the single aggregate ``vat_amount`` the journal
carries.

The defining properties (the catch-forever tests): sales at 15% and 0% land in
the correct boxes, and credit notes net the VAT down — net VAT = collected −
reversed.
"""
from conftest import (
    add_product,
    auth_headers,
    make_agent_account,
    make_client_account,
)


async def _sell(client, headers, pid, name, price, qty, vat_rate=15.0):
    resp = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": name, "price": price, "quantity": qty}],
            "payment_method": "cash",
            "vat_rate": vat_rate,
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _bucket(body, key):
    return next(b for b in body["buckets"] if b["key"] == key)


async def test_vat_summary_splits_standard_and_zero(client):
    """Named catch-forever test: 15% and 0% sales land in the correct boxes."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    std = await add_product(client_id, user["id"], name="Taxed", quantity=100, price=10.0)
    zero = await add_product(client_id, user["id"], name="ZeroRated", quantity=100, price=10.0)

    # 10 @ 10 standard → base 100, VAT 15.
    await _sell(client, headers, std, "Taxed", 10.0, 10, vat_rate=15.0)
    # 5 @ 10 zero-rated → base 50, VAT 0.
    await _sell(client, headers, zero, "ZeroRated", 10.0, 5, vat_rate=0.0)

    resp = await client.get("/api/v1/reports/vat-summary?days=30", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    standard = _bucket(body, "standard")
    assert standard["taxable_base"] == 100.0
    assert standard["vat_amount"] == 15.0
    assert standard["rate"] == 15.0

    zero_box = _bucket(body, "zero")
    assert zero_box["taxable_base"] == 50.0
    assert zero_box["vat_amount"] == 0.0

    # The exempt box is always present for ZATCA-return parity.
    assert _bucket(body, "exempt")["vat_amount"] == 0.0

    assert body["vat_collected"] == 15.0
    assert body["net_vat"] == 15.0
    assert body["total_taxable_base"] == 150.0


async def test_vat_summary_nets_credit_notes(client):
    """Named catch-forever test: net VAT = collected − reversed.

    Sell 10 @ 10 at 15% (VAT 15), then refund 4 units (credit note reverses VAT 6).
    The standard box nets to base 60 / VAT 9, and the summary reports collected 15,
    reversed 6, net 9.
    """
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Gadget", quantity=50, price=10.0)

    sale = await _sell(client, headers, pid, "Gadget", 10.0, 10, vat_rate=15.0)
    refund = await client.post(
        f"/api/v1/pos/transactions/{sale['id']}/refund",
        json={"lines": [{"product_id": pid, "quantity": 4}]},
        headers=headers,
    )
    assert refund.status_code == 200, refund.text

    resp = await client.get("/api/v1/reports/vat-summary", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    standard = _bucket(body, "standard")
    assert standard["taxable_base"] == 60.0   # 100 − 40
    assert standard["vat_amount"] == 9.0       # 15 − 6

    assert body["vat_collected"] == 15.0
    assert body["vat_reversed"] == 6.0
    assert body["net_vat"] == 9.0


async def test_vat_summary_csv_export(client):
    """CSV export carries the boxes and the net-VAT summary lines."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Item", quantity=20, price=10.0)
    await _sell(client, headers, pid, "Item", 10.0, 2, vat_rate=15.0)

    resp = await client.get("/api/v1/reports/vat-summary", headers=headers)
    body = resp.json()
    csv_text = body["csv_content"]
    assert "Standard-rated (15%)" in csv_text
    assert "Zero-rated (0%)" in csv_text
    assert "Net VAT payable" in csv_text


async def test_vat_summary_owner_scoped(client):
    """SEC-02: a client sees only its own VAT; an agent is 403."""
    user_a, token_a, client_a = await make_client_account(client)
    user_b, token_b, client_b = await make_client_account(client)

    pa = await add_product(client_a, user_a["id"], name="A", quantity=50, price=10.0)
    pb = await add_product(client_b, user_b["id"], name="B", quantity=50, price=20.0)
    await _sell(client, auth_headers(token_a), pa, "A", 10.0, 10, vat_rate=15.0)
    await _sell(client, auth_headers(token_b), pb, "B", 20.0, 10, vat_rate=15.0)

    resp_a = await client.get("/api/v1/reports/vat-summary", headers=auth_headers(token_a))
    body_a = resp_a.json()
    assert _bucket(body_a, "standard")["taxable_base"] == 100.0  # only A's, never B's 200

    _, agent_token, _ = await make_agent_account(client)
    resp_agent = await client.get("/api/v1/reports/vat-summary", headers=auth_headers(agent_token))
    assert resp_agent.status_code == 403, resp_agent.text
