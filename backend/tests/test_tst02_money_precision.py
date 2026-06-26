"""TST-02 — Money-precision suite (audit F2): rounding, three-way splits, stacked discounts.

The FIN-01/02/03 slices each fixed a float-drift defect and ship a focused test
(``core.money`` half-up, a single POS VAT line, service-level promo stacking).
The audit (F2) named three *money-math* scenarios that had no consolidated,
end-to-end coverage through the live POS sale path. This is that named suite:
one behavior per test, driven through ``POST /api/v1/pos/transaction``, asserting
penny-exact totals and exact tender reconciliation.

Each assertion is RED under the naive ``float`` + ``round()`` math the audit
flagged and GREEN on the Decimal (``core.money``, half-up) path now in place:

* additive drift — ``0.10 + 0.20`` subtotal VATs on the ``*.xx5`` boundary:
  ``round(0.30*0.15, 2) == 0.04`` (binary 0.0449…) vs Decimal half-up ``0.05``;
* three-way split — an amount due that doesn't divide evenly by three must
  reconcile to the penny across three tenders (no epsilon slop);
* stacked discounts — a coded discount + an auto-promotion fold into one taxable
  base; the promo's ``2.675 -> 2.68`` half-up survives the stack
  (``round(2.675, 2) == 2.67`` would short the merchant a penny and mis-VAT).
"""
import uuid

from conftest import add_product, auth_headers, make_client_account


async def _sale(client, headers, items, **extra):
    payload = {"items": items, "payment_method": "cash", **extra}
    return await client.post(
        "/api/v1/pos/transaction", json=payload, headers=headers
    )


async def _create_discount(client, headers, *, code, type, value):
    resp = await client.post(
        "/api/v1/entities/discounts",
        json={"code": code, "type": type, "value": value, "is_active": True},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _create_promotion(client, headers, **payload):
    resp = await client.post(
        "/api/v1/entities/promotions", json=payload, headers=headers
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Additive drift: 0.10 + 0.20 = 0.30, VAT lands on a *.xx5 half-up boundary
# ---------------------------------------------------------------------------
async def test_additive_subtotal_vats_penny_exact_half_up(client):
    """Two lines (0.10 + 0.20) subtotal to exactly 0.30; 15% VAT is 0.045 ->
    half-up 0.05, total 0.35. Float ``round(0.30*0.15, 2)`` yields 0.04 (the
    binary 0.0449…), total 0.34; Decimal half-up gives 0.05 / 0.35."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    a = await add_product(client_id, user["id"], name="Dime", quantity=10, price=0.10)
    b = await add_product(client_id, user["id"], name="Fifth", quantity=10, price=0.20)

    resp = await _sale(
        client, headers,
        [
            {"product_id": a, "name": "Dime", "price": 0.10, "quantity": 1},
            {"product_id": b, "name": "Fifth", "price": 0.20, "quantity": 1},
        ],
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["subtotal"] == 0.30
    assert body["vat_amount"] == 0.05
    assert body["total_amount"] == 0.35


# ---------------------------------------------------------------------------
# Three-way split: an amount due that doesn't divide by three reconciles exactly
# ---------------------------------------------------------------------------
async def test_three_way_split_reconciles_to_the_penny(client):
    """10.00 + 15% VAT = 11.50 due, split three ways (3.83 + 3.83 + 3.84) sums
    back to 11.50 to the penny and is accepted. The uneven remainder leg must
    land exactly — the tender check is exact, with no epsilon."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Plate", quantity=10, price=10.0)

    resp = await _sale(
        client, headers,
        [{"product_id": pid, "name": "Plate", "price": 10.0, "quantity": 1}],
        payments=[
            {"method": "cash", "amount": 3.83},
            {"method": "card", "amount": 3.83},
            {"method": "card", "amount": 3.84},
        ],
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["total_amount"] == 11.50


async def test_three_way_split_one_penny_short_is_rejected(client):
    """The same 11.50 due, paid three ways but a penny short (3.83 x 3 = 11.49),
    is rejected — exact reconciliation across more than two tenders, no epsilon
    slop that would let a penny-short split slip through."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Plate", quantity=10, price=10.0)

    resp = await _sale(
        client, headers,
        [{"product_id": pid, "name": "Plate", "price": 10.0, "quantity": 1}],
        payments=[
            {"method": "cash", "amount": 3.83},
            {"method": "card", "amount": 3.83},
            {"method": "card", "amount": 3.83},
        ],
    )
    assert resp.status_code == 400, resp.text
    assert "does not match" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Stacked discounts: a coded discount + an auto-promotion fold into one base
# ---------------------------------------------------------------------------
async def test_stacked_coded_and_promo_discount_penny_exact(client):
    """A SAR 1.00 coded discount stacks with a 50%-off-line promotion on a 5.35
    line: 1.00 + 2.675->2.68 = 3.68 off, taxable 1.67, VAT 0.2505->0.25, total
    1.92. The promo's half-up (``round(2.675, 2) == 2.67`` float trap) survives
    the stack — naive float would discount 3.67, VAT a 1.68 base and total 1.93,
    shorting the merchant a penny."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Combo", quantity=10, price=5.35)

    code = f"SAR1_{uuid.uuid4().hex[:6]}"
    await _create_discount(client, headers, code=code, type="fixed", value=1.0)
    await _create_promotion(
        client, headers, name="half off combo", kind="line",
        disc_type="percentage", value=50.0, product_id=pid,
    )

    resp = await _sale(
        client, headers,
        [{"product_id": pid, "name": "Combo", "price": 5.35, "quantity": 1}],
        discount_code=code,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["subtotal"] == 5.35
    # 1.00 coded + 2.68 promo, summed as exact 2dp pennies — not 3.67.
    assert body["discount_amount"] == 3.68
    # VAT on the clamped taxable base (5.35 - 3.68 = 1.67): 0.2505 -> 0.25.
    assert body["vat_amount"] == 0.25
    assert body["total_amount"] == 1.92
    # The promo's penny-exact contribution surfaces to the cashier.
    applied = body.get("applied_promotions") or []
    assert [p["name"] for p in applied] == ["half off combo"]
    assert applied[0]["amount"] == 2.68
