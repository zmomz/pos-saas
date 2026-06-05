"""Phase 7 — refund/void + discount reports (F-071 / RPT-08).

A manager could only see refunds/voids/discounts per-shift inside the Z-report.
These two reports generalize that bucketing across a date window and add the audit
dimension the Z-report omits — WHO did it, WHY, and WHEN:

* ``GET /reports/refunds-voids`` — each refund (credit note) and void with actor,
  reason, amount, timestamp;
* ``GET /reports/discounts`` — each discounted sale with actor, code, amount.

The named catch-forever test (``test_void_and_discount_show_actor_reason_amount``)
asserts a void with a reason and a discounted sale each surface with the actor /
reason / amount. Both are owner-scoped (SEC-02) and an agent is 403.
"""
import uuid

from conftest import (
    add_product,
    auth_headers,
    make_agent_account,
    make_client_account,
)


async def _sale(client, headers, pid, *, price=10.0, qty=2, discount_code=None,
                discount_amount=None):
    body = {
        "items": [{"product_id": pid, "name": "Cola", "price": price, "quantity": qty}],
        "payment_method": "cash",
    }
    if discount_code is not None:
        body["discount_code"] = discount_code
    if discount_amount is not None:
        body["discount_amount"] = discount_amount
    resp = await client.post("/api/v1/pos/transaction", json=body, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _create_discount(client, headers, *, code, value=10.0):
    resp = await client.post(
        "/api/v1/entities/discounts",
        json={"code": code, "type": "fixed", "value": value, "is_active": True},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Refunds / voids report
# ---------------------------------------------------------------------------
async def test_void_and_discount_show_actor_reason_amount(client):
    """Named catch-forever test: a void (with reason) and a discounted sale each
    appear with actor / reason / amount."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=100, price=10.0)

    # A plain sale we then void, with a reason.
    to_void = await _sale(client, headers, pid, qty=2)
    voided = await client.post(
        f"/api/v1/pos/transactions/{to_void['id']}/void",
        json={"reason": "wrong item"},
        headers=headers,
    )
    assert voided.status_code == 200, voided.text

    # A manual discount sale (the owner holds pos.discount by default).
    discounted = await _sale(client, headers, pid, qty=2, discount_amount=5.0)
    assert abs(discounted["discount_amount"] - 5.0) < 0.01

    # --- Refunds/voids report shows the void with actor + reason + amount ---
    rv = (await client.get("/api/v1/reports/refunds-voids", headers=headers)).json()
    void_rows = [r for r in rv["rows"] if r["type"] == "void"]
    assert len(void_rows) == 1
    vr = void_rows[0]
    assert vr["transaction_id"] == to_void["id"]
    assert vr["reason"] == "wrong item"
    assert vr["actor"] == user["name"] or vr["actor"] == user["id"]
    assert abs(vr["amount"] - to_void["total_amount"]) < 0.01
    assert rv["void_count"] == 1

    # --- Discount report shows the discounted sale with actor + amount ---
    dr = (await client.get("/api/v1/reports/discounts", headers=headers)).json()
    assert dr["discount_count"] == 1
    row = dr["rows"][0]
    assert row["transaction_id"] == discounted["id"]
    assert abs(row["discount_amount"] - 5.0) < 0.01
    assert row["is_manual"] is True       # a codeless override
    assert row["actor"] == user["name"] or row["actor"] == user["id"]
    assert abs(dr["discount_total"] - 5.0) < 0.01


async def test_refund_appears_with_amount_and_original_invoice(client):
    """A partial refund issues a credit note that surfaces in the report with the
    positive amount reversed and a pointer to the original invoice."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Gadget", quantity=50, price=10.0)

    sale = await _sale(client, headers, pid, qty=4)  # 4 @ 10 → total 46.0 (15% VAT off? no VAT set)
    refund = await client.post(
        f"/api/v1/pos/transactions/{sale['id']}/refund",
        json={"lines": [{"product_id": pid, "quantity": 2}]},
        headers=headers,
    )
    assert refund.status_code == 200, refund.text

    rv = (await client.get("/api/v1/reports/refunds-voids", headers=headers)).json()
    refund_rows = [r for r in rv["rows"] if r["type"] == "refund"]
    assert len(refund_rows) == 1
    rr = refund_rows[0]
    assert rr["amount"] > 0                       # reported positive, not the stored negative
    assert rr["original_invoice"] == sale["invoice_number"]
    assert rv["refund_count"] == 1
    assert rv["refund_total"] > 0


async def test_coded_discount_surfaces_the_code(client):
    """A coded discount persists the code so the report shows it (not 'manual')."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Item", quantity=100, price=50.0)
    code = f"FLAT5_{uuid.uuid4().hex[:6]}"
    await _create_discount(client, headers, code=code, value=5.0)

    await _sale(client, headers, pid, price=50.0, qty=2, discount_code=code)

    dr = (await client.get("/api/v1/reports/discounts", headers=headers)).json()
    assert dr["discount_count"] == 1
    row = dr["rows"][0]
    assert row["code"] == code
    assert row["is_manual"] is False
    assert abs(row["discount_amount"] - 5.0) < 0.01


async def test_refunds_voids_csv_export(client):
    """CSV export carries the header rows and the count/total summary lines."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=20, price=10.0)
    sale = await _sale(client, headers, pid, qty=1)
    await client.post(
        f"/api/v1/pos/transactions/{sale['id']}/void",
        json={"reason": "test"},
        headers=headers,
    )

    rv = (await client.get("/api/v1/reports/refunds-voids", headers=headers)).json()
    csv_text = rv["csv_content"]
    assert "Refunds & voids" in csv_text
    assert "Void count" in csv_text
    assert "Refund count" in csv_text


# ---------------------------------------------------------------------------
# Owner-scoping (SEC-02)
# ---------------------------------------------------------------------------
async def test_reports_are_owner_scoped_and_agent_forbidden(client):
    user_a, token_a, client_a = await make_client_account(client)
    user_b, token_b, client_b = await make_client_account(client)

    pa = await add_product(client_a, user_a["id"], name="A", quantity=50, price=10.0)
    pb = await add_product(client_b, user_b["id"], name="B", quantity=50, price=20.0)

    # A voids one sale + applies one discount; B does its own.
    sale_a = await _sale(client, auth_headers(token_a), pa, qty=1)
    await client.post(
        f"/api/v1/pos/transactions/{sale_a['id']}/void",
        json={"reason": "A reason"},
        headers=auth_headers(token_a),
    )
    await _sale(client, auth_headers(token_a), pa, qty=1, discount_amount=3.0)

    sale_b = await _sale(client, auth_headers(token_b), pb, qty=1)
    await client.post(
        f"/api/v1/pos/transactions/{sale_b['id']}/void",
        json={"reason": "B reason"},
        headers=auth_headers(token_b),
    )
    await _sale(client, auth_headers(token_b), pb, qty=1, discount_amount=7.0)

    # A only ever sees A's void/discount, never B's.
    rv_a = (await client.get("/api/v1/reports/refunds-voids", headers=auth_headers(token_a))).json()
    assert rv_a["void_count"] == 1
    assert all(r["transaction_id"] == sale_a["id"] for r in rv_a["rows"] if r["type"] == "void")
    assert {r["reason"] for r in rv_a["rows"] if r["type"] == "void"} == {"A reason"}

    dr_a = (await client.get("/api/v1/reports/discounts", headers=auth_headers(token_a))).json()
    assert dr_a["discount_count"] == 1
    assert abs(dr_a["discount_total"] - 3.0) < 0.01  # never B's 7.0

    # An agent cannot view either report.
    _, agent_token, _ = await make_agent_account(client)
    assert (await client.get("/api/v1/reports/refunds-voids", headers=auth_headers(agent_token))).status_code == 403
    assert (await client.get("/api/v1/reports/discounts", headers=auth_headers(agent_token))).status_code == 403
