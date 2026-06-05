"""F-044 / FIN-04 / POS-09 — cash drawer movements tied to the shift.

A shift's drawer doesn't only hold opening float + cash sales − cash refunds: a
cashier also pays cash in (extra float), pays cash out (petty cash / supplier from
the till) and skims a cash-drop to the safe. These movements are recorded against
the open shift and **folded into the drawer reconciliation** (close + Z/X-report),
so the expected cash is honest and RPT-06's payouts line has data.

Proves:
* a pay-out reduces expected cash and surfaces in the Z-report (and close);
* pay-in adds, cash-drop subtracts;
* a movement requires an open shift (404) and a valid type/amount (400/422);
* movements are owner-scoped (one client never sees another's, SEC-02).
"""
from conftest import add_product, auth_headers, make_client_account


async def _open_shift(client, headers, opening_cash=100.0):
    resp = await client.post(
        "/api/v1/production/shifts/open",
        json={"opening_cash": opening_cash},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _cash_sale(client, headers, pid, *, price=10.0, qty=2):
    resp = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Cola", "price": price, "quantity": qty}],
            "payment_method": "cash",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _movement(client, headers, mtype, amount, reason=None):
    return await client.post(
        "/api/v1/production/shifts/movements",
        json={"movement_type": mtype, "amount": amount, "reason": reason},
        headers=headers,
    )


async def test_pay_out_reduces_expected_cash_and_shows_in_zreport(client):
    """Open 100, ring a 23.00 cash sale, pay 10.00 out of the till for petty cash.
    Expected drawer = 100 + 23 − 10 = 113 (NOT 123). The Z-report carries the
    pay-out, and closing on 113 reconciles balanced."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=50, price=10.0)

    open_resp = await _open_shift(client, headers, opening_cash=100.0)
    shift_id = open_resp["id"]
    await _cash_sale(client, headers, pid, qty=2)  # 2*10 + 15% = 23.00 cash

    mv = await _movement(client, headers, "pay_out", 10.0, reason="Petty cash — water")
    assert mv.status_code == 200, mv.text
    body = mv.json()
    assert abs(body["pay_out"] - 10.0) < 0.01
    assert abs(body["expected_cash"] - 113.0) < 0.01  # 100 + 23 − 10

    # The movement is listed for the open shift.
    listed = (await client.get("/api/v1/production/shifts/movements", headers=headers)).json()
    assert listed["total"] == 1
    assert listed["movements"][0]["movement_type"] == "pay_out"
    assert abs(listed["pay_out"] - 10.0) < 0.01

    # X-report (still open) folds the pay-out into the drawer expectation.
    x = (await client.get("/api/v1/reports/zreport", headers=headers)).json()
    assert abs(x["cash"]["pay_out"] - 10.0) < 0.01
    assert abs(x["cash"]["expected_cash"] - 113.0) < 0.01

    # Close on the expected drawer → balanced, and the close response carries it.
    close = await client.post(
        "/api/v1/production/shifts/close",
        json={"closing_cash": 113.0},
        headers=headers,
    )
    assert close.status_code == 200, close.text
    cbody = close.json()
    assert abs(cbody["expected_cash"] - 113.0) < 0.01
    assert abs(cbody["pay_out"] - 10.0) < 0.01
    assert cbody["reconciliation"] == "balanced"

    # The closed-shift Z-report still reports the pay-out.
    z = (await client.get(f"/api/v1/reports/zreport?shift_id={shift_id}", headers=headers)).json()
    assert z["report_type"] == "Z"
    assert abs(z["cash"]["pay_out"] - 10.0) < 0.01
    assert abs(z["cash"]["expected_cash"] - 113.0) < 0.01


async def test_pay_in_adds_and_cash_drop_subtracts(client):
    """Pay-in adds to the drawer; cash-drop (skim to the safe) takes from it."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    await _open_shift(client, headers, opening_cash=200.0)

    assert (await _movement(client, headers, "pay_in", 50.0)).status_code == 200
    drop = await _movement(client, headers, "cash_drop", 30.0)
    assert drop.status_code == 200

    body = drop.json()
    assert abs(body["pay_in"] - 50.0) < 0.01
    assert abs(body["cash_drops"] - 30.0) < 0.01
    # 200 + 50 (pay-in) − 30 (cash-drop) = 220, no sales.
    assert abs(body["expected_cash"] - 220.0) < 0.01


async def test_cash_movement_requires_open_shift(client):
    user, token, _ = await make_client_account(client)
    headers = auth_headers(token)
    # No shift opened.
    resp = await _movement(client, headers, "pay_out", 5.0)
    assert resp.status_code == 404, resp.text


async def test_cash_movement_rejects_unknown_type_and_nonpositive_amount(client):
    user, token, _ = await make_client_account(client)
    headers = auth_headers(token)
    await _open_shift(client, headers, opening_cash=100.0)

    bad_type = await _movement(client, headers, "withdrawal", 5.0)
    assert bad_type.status_code == 400, bad_type.text

    # amount must be a positive magnitude (Field gt=0 → 422 validation error).
    zero = await _movement(client, headers, "pay_out", 0.0)
    assert zero.status_code == 422, zero.text


async def test_cash_movements_are_owner_scoped(client):
    """One client can neither list nor reconcile another client's drawer movements."""
    user_a, token_a, client_id_a = await make_client_account(client)
    headers_a = auth_headers(token_a)
    open_a = await _open_shift(client, headers_a, opening_cash=100.0)
    a_shift_id = open_a["id"]
    assert (await _movement(client, headers_a, "pay_out", 10.0)).status_code == 200

    # Client B asks for client A's shift movements → filtered by user_id → empty.
    _, token_b, _ = await make_client_account(client)
    headers_b = auth_headers(token_b)
    cross = (
        await client.get(
            f"/api/v1/production/shifts/movements?shift_id={a_shift_id}", headers=headers_b
        )
    ).json()
    assert cross["total"] == 0
    assert cross["movements"] == []
