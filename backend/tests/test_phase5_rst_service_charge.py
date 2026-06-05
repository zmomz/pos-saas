"""F-061 — Service charge outside the VAT base.

A restaurant can apply an optional **service-charge %** to an order ticket. Like a
tip (POS-13/F-012), the service charge is computed **OUTSIDE the VAT base**: VAT is
charged on the goods only, the service charge is a separate non-taxable line, and
the amount the tenders must cover is invoice total (goods + VAT) + service charge
(+ tip). The bill is computed by ``…/order-tickets/{id}/check`` — the normalized
cart the settle path (F-059) later mints a ZATCA invoice from.

Catches forever (per the slice F-061):
* a ticket with a service charge: VAT is on the goods only, the invoice total stays
  goods+VAT, the service charge appears as its own non-taxable line, and the amount
  due = total + service charge (+ tip);
* applying a service charge never inflates the taxable base or the VAT;
* a negative service charge is rejected;
* the service charge / check is owner-scoped and behind the restaurant double-gate.

The named "catch-forever" test required by the slice is
``test_service_charge_excluded_from_vat_base_and_shown_on_invoice``.
"""
from conftest import add_product, auth_headers, make_client_account


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _make_table(client, token, name="T1"):
    return (
        await client.post(
            "/api/v1/restaurant/tables",
            json={"name": name, "seats": 4},
            headers=auth_headers(token),
        )
    ).json()["id"]


async def _open_dine_in(client, token, table_id):
    return (
        await client.post(
            "/api/v1/restaurant/order-tickets",
            json={"order_type": "dine_in", "table_id": table_id},
            headers=auth_headers(token),
        )
    ).json()["id"]


async def _add_line(client, token, ticket_id, product_id, qty=1):
    resp = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/items",
        json={"product_id": product_id, "qty": qty},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Named slice test: service charge is excluded from the VAT base and shown
# as its own line on the (eventual) invoice / the check.
# ---------------------------------------------------------------------------
async def test_service_charge_excluded_from_vat_base_and_shown_on_invoice(client):
    user, token, client_id = await make_client_account(client, business_type="restaurant")
    headers = auth_headers(token)
    table_id = await _make_table(client, token, name="S1")
    ticket_id = await _open_dine_in(client, token, table_id)

    # 100 SAR of goods on the ticket.
    pid = await add_product(client_id, user["id"], name="Shawarma", quantity=50, price=100.0)
    await _add_line(client, token, ticket_id, pid, qty=1)

    # Apply a 10% service charge.
    sc = await client.put(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/service-charge",
        json={"service_charge_pct": 10},
        headers=headers,
    )
    assert sc.status_code == 200, sc.text
    assert abs(sc.json()["service_charge_pct"] - 10) < 0.001

    check = await client.get(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/check", headers=headers
    )
    assert check.status_code == 200, check.text
    body = check.json()

    # The goods are the ONLY taxable base: VAT is 15% of the 100 goods, and the
    # invoice total stays goods+VAT — the service charge does not touch it.
    assert abs(body["subtotal"] - 100.0) < 0.01
    assert abs(body["vat_amount"] - 15.0) < 0.01
    assert abs(body["total_amount"] - 115.0) < 0.01

    # The service charge is its own non-taxable line, OUTSIDE the VAT base.
    assert abs(body["service_charge"]["pct"] - 10.0) < 0.01
    assert abs(body["service_charge"]["amount"] - 10.0) < 0.01
    assert body["service_charge"]["taxable"] is False

    # The amount the tenders must cover = invoice total + service charge.
    assert abs(body["amount_due"] - 125.0) < 0.01


# ---------------------------------------------------------------------------
# Applying a service charge never inflates the taxable amount or the VAT.
# ---------------------------------------------------------------------------
async def test_service_charge_does_not_change_vat_or_taxable_base(client):
    user, token, client_id = await make_client_account(client, business_type="restaurant")
    headers = auth_headers(token)
    table_id = await _make_table(client, token, name="S2")
    ticket_id = await _open_dine_in(client, token, table_id)
    pid = await add_product(client_id, user["id"], name="Burger", quantity=50, price=200.0)
    await _add_line(client, token, ticket_id, pid, qty=1)

    # Check with NO service charge first.
    before = (
        await client.get(
            f"/api/v1/restaurant/order-tickets/{ticket_id}/check", headers=headers
        )
    ).json()
    assert abs(before["service_charge"]["amount"] - 0.0) < 0.01
    assert abs(before["amount_due"] - before["total_amount"]) < 0.01

    # Apply a 12% service charge and re-check.
    await client.put(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/service-charge",
        json={"service_charge_pct": 12},
        headers=headers,
    )
    after = (
        await client.get(
            f"/api/v1/restaurant/order-tickets/{ticket_id}/check", headers=headers
        )
    ).json()

    # The taxable base and the VAT are identical before and after the charge.
    assert abs(after["subtotal"] - before["subtotal"]) < 0.01
    assert abs(after["vat_amount"] - before["vat_amount"]) < 0.01
    assert abs(after["total_amount"] - before["total_amount"]) < 0.01
    # Only the service charge (outside VAT) and the amount due moved.
    assert abs(after["service_charge"]["amount"] - 24.0) < 0.01  # 12% of 200
    assert abs(after["amount_due"] - (after["total_amount"] + 24.0)) < 0.01


# ---------------------------------------------------------------------------
# Tender validation: amount due covers invoice total + tip + service charge.
# ---------------------------------------------------------------------------
async def test_amount_due_covers_total_tip_and_service_charge(client):
    user, token, client_id = await make_client_account(client, business_type="restaurant")
    headers = auth_headers(token)
    table_id = await _make_table(client, token, name="S3")
    ticket_id = await _open_dine_in(client, token, table_id)
    pid = await add_product(client_id, user["id"], name="Salad", quantity=50, price=100.0)
    await _add_line(client, token, ticket_id, pid, qty=1)

    await client.put(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/service-charge",
        json={"service_charge_pct": 10},
        headers=headers,
    )

    # A 20 SAR tip on top of the 10% service charge.
    check = (
        await client.get(
            f"/api/v1/restaurant/order-tickets/{ticket_id}/check",
            params={"tip_amount": 20},
            headers=headers,
        )
    ).json()

    # goods 100 + VAT 15 = 115 invoice; + 10 service charge + 20 tip = 145 due.
    assert abs(check["total_amount"] - 115.0) < 0.01
    assert abs(check["service_charge"]["amount"] - 10.0) < 0.01
    assert abs(check["tip_amount"] - 20.0) < 0.01
    assert abs(check["amount_due"] - 145.0) < 0.01


async def test_negative_service_charge_rejected(client):
    _user, token, _cid = await make_client_account(client, business_type="restaurant")
    headers = auth_headers(token)
    table_id = await _make_table(client, token, name="S4")
    ticket_id = await _open_dine_in(client, token, table_id)

    resp = await client.put(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/service-charge",
        json={"service_charge_pct": -5},
        headers=headers,
    )
    assert resp.status_code == 400, resp.text


async def test_negative_tip_on_check_rejected(client):
    _user, token, _cid = await make_client_account(client, business_type="restaurant")
    headers = auth_headers(token)
    table_id = await _make_table(client, token, name="S5")
    ticket_id = await _open_dine_in(client, token, table_id)

    # tip_amount has a ge=0 query constraint → 422 before the handler runs.
    resp = await client.get(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/check",
        params={"tip_amount": -1},
        headers=headers,
    )
    assert resp.status_code == 422, resp.text


# ---------------------------------------------------------------------------
# Owner scoping (SEC-02) and the restaurant double-gate.
# ---------------------------------------------------------------------------
async def test_service_charge_owner_scoped(client):
    _u1, token1, _c1 = await make_client_account(client, business_type="restaurant")
    _u2, token2, _c2 = await make_client_account(client, business_type="restaurant")
    table_id = await _make_table(client, token1, name="O1")
    ticket_id = await _open_dine_in(client, token1, table_id)

    # A second client cannot set the first's service charge...
    set_resp = await client.put(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/service-charge",
        json={"service_charge_pct": 10},
        headers=auth_headers(token2),
    )
    assert set_resp.status_code == 404, set_resp.text
    # ...nor read its check.
    check_resp = await client.get(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/check",
        headers=auth_headers(token2),
    )
    assert check_resp.status_code == 404, check_resp.text


async def test_service_charge_requires_restaurant_business_type(client):
    _user, token, _cid = await make_client_account(client, business_type="retail")
    resp = await client.put(
        "/api/v1/restaurant/order-tickets/1/service-charge",
        json={"service_charge_pct": 10},
        headers=auth_headers(token),
    )
    assert resp.status_code == 403, resp.text
