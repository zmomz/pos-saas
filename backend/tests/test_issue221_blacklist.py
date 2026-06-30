"""M5·CRM (#221) — customer blacklist (tracer bullet).

Acceptance: "blacklist function." A merchant can blacklist a customer (with a
reason), the flag is surfaced on the customer record, can be cleared, and is
owner-scoped (SEC-02). A blacklisted customer is blocked at sale time so they can
no longer transact — the server is authoritative.
"""
from conftest import add_product, auth_headers, make_client_account


async def _make_customer(client, token, name="Blacklist Cust"):
    resp = await client.post(
        "/api/v1/entities/customers", json={"name": name}, headers=auth_headers(token)
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_blacklist_flags_customer_and_can_be_cleared(client):
    _, token, _ = await make_client_account(client)
    cust_id = await _make_customer(client, token)

    # Not blacklisted to start.
    g0 = await client.get(
        f"/api/v1/entities/customers/{cust_id}", headers=auth_headers(token)
    )
    assert g0.status_code == 200, g0.text
    assert g0.json()["blacklisted"] is False
    assert g0.json()["blacklist_reason"] is None

    # Blacklist with a reason.
    b = await client.post(
        f"/api/v1/entities/customers/{cust_id}/blacklist",
        json={"reason": "chargeback fraud"},
        headers=auth_headers(token),
    )
    assert b.status_code == 200, b.text
    assert b.json()["blacklisted"] is True
    assert b.json()["blacklist_reason"] == "chargeback fraud"

    # The flag persists on a fresh read.
    g1 = await client.get(
        f"/api/v1/entities/customers/{cust_id}", headers=auth_headers(token)
    )
    assert g1.json()["blacklisted"] is True
    assert g1.json()["blacklist_reason"] == "chargeback fraud"

    # Clear it.
    c = await client.request(
        "DELETE",
        f"/api/v1/entities/customers/{cust_id}/blacklist",
        headers=auth_headers(token),
    )
    assert c.status_code == 200, c.text
    assert c.json()["blacklisted"] is False
    assert c.json()["blacklist_reason"] is None


async def test_blacklist_is_owner_scoped(client):
    _, token_a, _ = await make_client_account(client)
    _, token_b, _ = await make_client_account(client)
    cust_id = await _make_customer(client, token_a)

    # Tenant B cannot blacklist tenant A's customer …
    b = await client.post(
        f"/api/v1/entities/customers/{cust_id}/blacklist",
        json={"reason": "nope"},
        headers=auth_headers(token_b),
    )
    assert b.status_code == 404, b.text

    # … nor clear a blacklist on it.
    await client.post(
        f"/api/v1/entities/customers/{cust_id}/blacklist",
        json={"reason": "real"},
        headers=auth_headers(token_a),
    )
    c = await client.request(
        "DELETE",
        f"/api/v1/entities/customers/{cust_id}/blacklist",
        headers=auth_headers(token_b),
    )
    assert c.status_code == 404, c.text

    # Tenant A's flag is untouched by B's attempts.
    g = await client.get(
        f"/api/v1/entities/customers/{cust_id}", headers=auth_headers(token_a)
    )
    assert g.json()["blacklisted"] is True
    assert g.json()["blacklist_reason"] == "real"


async def test_blacklisted_customer_is_blocked_at_sale_time(client):
    user, token, client_id = await make_client_account(client)
    pid = await add_product(client_id, user["id"], quantity=100, price=10.0)
    cust_id = await _make_customer(client, token)

    sale_body = {
        "items": [{"product_id": pid, "name": "Widget", "price": 10.0, "quantity": 1}],
        "payment_method": "cash",
        "customer_id": cust_id,
    }

    # Blacklist the customer → the sale is rejected server-side.
    await client.post(
        f"/api/v1/entities/customers/{cust_id}/blacklist",
        json={"reason": "fraud"},
        headers=auth_headers(token),
    )
    blocked = await client.post(
        "/api/v1/pos/transaction", json=sale_body, headers=auth_headers(token)
    )
    assert blocked.status_code == 403, blocked.text
    assert "blacklist" in blocked.json()["detail"].lower()

    # Lift the blacklist → the same sale goes through.
    await client.request(
        "DELETE",
        f"/api/v1/entities/customers/{cust_id}/blacklist",
        headers=auth_headers(token),
    )
    ok = await client.post(
        "/api/v1/pos/transaction", json=sale_body, headers=auth_headers(token)
    )
    assert ok.status_code == 200, ok.text
