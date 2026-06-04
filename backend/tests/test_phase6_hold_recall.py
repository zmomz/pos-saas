"""F-010 / POS-10 — park/hold & recall of a sale.

A cashier can suspend the current cart as a *held* ticket (so the next customer
can be served) and recall it later to ring it up. A held ticket has NO fiscal
side effect — it consumes no invoice counter, gets no ZATCA stamp, does not
deduct stock, and must never count as revenue — until it is recalled and rung up
through the normal atomic sale path.

These tests prove:
* holding a cart lists it under ``GET /pos/held`` with the right item count and
  deducts no stock; recalling it returns the items and clears it from the list;
* a held ticket does not inflate ``/reports/sales-summary`` (it is not a sale);
* hold/recall are owner-scoped — one client cannot see or recall another's
  held tickets (SEC-02);
* an empty cart cannot be held.
"""
from conftest import (
    add_product,
    auth_headers,
    get_product_quantity,
    make_client_account,
)


def _items(pid, *, price=10.0, qty=2):
    return [{"product_id": pid, "name": "Cola", "price": price, "quantity": qty}]


# ---------------------------------------------------------------------------
# Hold → list → recall round-trip (the named "catch forever" test)
# ---------------------------------------------------------------------------
async def test_hold_lists_then_recall_restores_and_clears(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=50, price=10.0)

    # Park a 3-unit cart.
    resp = await client.post(
        "/api/v1/pos/hold",
        json={"items": _items(pid, qty=3), "label": "Table 5"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    held = resp.json()
    held_id = held["id"]
    assert held["item_count"] == 3
    assert held["label"] == "Table 5"

    # Holding deducts NO stock — the sale hasn't happened yet.
    assert await get_product_quantity(pid) == 50

    # It shows up under the held list.
    listing = (await client.get("/api/v1/pos/held", headers=headers)).json()
    assert listing["total"] == 1
    assert listing["items"][0]["id"] == held_id

    # Recall restores the cart contents...
    recalled = await client.post(f"/api/v1/pos/recall/{held_id}", headers=headers)
    assert recalled.status_code == 200, recalled.text
    body = recalled.json()
    assert body["label"] == "Table 5"
    assert len(body["items"]) == 1
    assert body["items"][0]["product_id"] == pid
    assert body["items"][0]["quantity"] == 3

    # ...and clears it from the held list.
    listing2 = (await client.get("/api/v1/pos/held", headers=headers)).json()
    assert listing2["total"] == 0

    # Recalling an already-recalled ticket is a 404.
    assert (await client.post(f"/api/v1/pos/recall/{held_id}", headers=headers)).status_code == 404


# ---------------------------------------------------------------------------
# A held ticket is not revenue
# ---------------------------------------------------------------------------
async def test_held_ticket_excluded_from_sales_summary(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=50, price=10.0)

    # Only a held ticket so far — no completed sale.
    await client.post(
        "/api/v1/pos/hold", json={"items": _items(pid, qty=2)}, headers=headers
    )
    summary = (
        await client.get("/api/v1/reports/sales-summary?days=30", headers=headers)
    ).json()
    assert summary["total_sales"] == 0
    assert summary["total_transactions"] == 0

    # Ring a real sale; now revenue appears and the held ticket still doesn't count.
    sale = await client.post(
        "/api/v1/pos/transaction",
        json={"items": _items(pid, qty=2), "payment_method": "cash"},
        headers=headers,
    )
    assert sale.status_code == 200, sale.text
    sale_total = sale.json()["total_amount"]
    summary2 = (
        await client.get("/api/v1/reports/sales-summary?days=30", headers=headers)
    ).json()
    assert summary2["total_transactions"] == 1
    assert abs(summary2["total_sales"] - sale_total) < 0.01


# ---------------------------------------------------------------------------
# Owner scoping (SEC-02)
# ---------------------------------------------------------------------------
async def test_recall_is_owner_scoped(client):
    user_a, token_a, client_a = await make_client_account(client)
    pid_a = await add_product(client_a, user_a["id"], quantity=10, price=10.0)
    held = (
        await client.post(
            "/api/v1/pos/hold",
            json={"items": _items(pid_a, qty=1)},
            headers=auth_headers(token_a),
        )
    ).json()
    held_id = held["id"]

    # A different client can neither see nor recall A's held ticket.
    _, token_b, _ = await make_client_account(client)
    headers_b = auth_headers(token_b)
    listing_b = (await client.get("/api/v1/pos/held", headers=headers_b)).json()
    assert listing_b["total"] == 0
    assert (
        await client.post(f"/api/v1/pos/recall/{held_id}", headers=headers_b)
    ).status_code == 404

    # A's ticket is untouched and still recallable by A.
    assert (
        await client.post(f"/api/v1/pos/recall/{held_id}", headers=auth_headers(token_a))
    ).status_code == 200


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
async def test_hold_empty_cart_rejected(client):
    _, token, _ = await make_client_account(client)
    resp = await client.post(
        "/api/v1/pos/hold", json={"items": []}, headers=auth_headers(token)
    )
    assert resp.status_code == 400
