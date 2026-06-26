"""FIN-09 — single-use discount-code redemption is atomic with the sale.

A unique, single-use discount code (``DiscountCodes``, distinct from the reusable
``Discounts`` rule) must be consumed *iff* the sale that applies it commits. The
old behaviour burned the code in its own committed transaction (the standalone
/redeem endpoint), so a code was spent even when the sale that was supposed to use
it never went through — and a failed sale silently lost the code.

This pins the corrected contract through the POS sale path:
* applying a single-use code to a sale that COMMITS consumes the one use (priced
  server-side) and a second sale with the same code is rejected (one-shot);
* applying a single-use code to a sale that ABORTS (e.g. oversell rolls the whole
  sale back) leaves the code intact — it still redeems on a later good sale.
"""
from conftest import (
    add_product,
    auth_headers,
    make_client_account,
)


async def _generate_code(client, headers, *, type="percentage", value=10.0, **fields):
    payload = {"count": 1, "type": type, "value": value}
    payload.update(fields)
    resp = await client.post(
        "/api/v1/entities/discount-codes/generate", json=payload, headers=headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["codes"][0]["code"]


async def _sale(client, headers, pid, *, qty, price, discount_code=None):
    body = {
        "items": [{"product_id": pid, "name": "Cola", "price": price, "quantity": qty}],
        "payment_method": "cash",
    }
    if discount_code is not None:
        body["discount_code"] = discount_code
    return await client.post("/api/v1/pos/transaction", json=body, headers=headers)


# ---------------------------------------------------------------------------
# A committed sale consumes the one use; a second sale with the code is rejected.
# ---------------------------------------------------------------------------
async def test_single_use_code_consumed_when_sale_commits(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=10, price=100.0)
    code = await _generate_code(client, headers, type="percentage", value=10.0)

    first = await _sale(client, headers, pid, qty=1, price=100.0, discount_code=code)
    assert first.status_code == 200, first.text
    # 10% of a 100 subtotal, priced server-side from the code rule.
    assert abs(first.json()["discount_amount"] - 10.0) < 0.01

    # One-shot: the code was consumed by the committed sale, so it cannot be reused.
    second = await _sale(client, headers, pid, qty=1, price=100.0, discount_code=code)
    assert second.status_code == 400, second.text


# ---------------------------------------------------------------------------
# A rolled-back sale leaves the code intact (no silent burn).
# ---------------------------------------------------------------------------
async def test_single_use_code_intact_when_sale_aborts(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=2, price=100.0)
    code = await _generate_code(client, headers, type="percentage", value=10.0)

    # Oversell rolls the whole sale back — including the code consumption.
    aborted = await _sale(client, headers, pid, qty=10, price=100.0, discount_code=code)
    assert aborted.status_code == 400, aborted.text

    # The code was NOT spent by the failed sale: it still redeems on a good sale.
    good = await _sale(client, headers, pid, qty=1, price=100.0, discount_code=code)
    assert good.status_code == 200, good.text
    assert abs(good.json()["discount_amount"] - 10.0) < 0.01
