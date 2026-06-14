"""ISSUE-068 (P2 catalog) — soft-delete (archive) products.

Deleting a product archives it (``is_active=False``) rather than hard-deleting
referenced rows, so historical sales/reports stay intact and the SKU can be
restored. These behaviours are pinned end-to-end through the public HTTP API:

* an archived product disappears from the active catalog / POS list
  (``GET /products/list``, which both the catalog screen and the POS terminal
  call) — but a past sale that referenced it still resolves;
* the management screen can opt in to see archived rows (``include_archived``);
* an archived product can be restored and reappears in the active list;
* restore is owner-scoped (a merchant cannot restore another merchant's product).
"""
from conftest import add_product, auth_headers, make_client_account


async def _list_names(client, token, **params) -> list[str]:
    query = "&".join(f"{k}={v}" for k, v in params.items())
    url = "/api/v1/products/list" + (f"?{query}" if query else "")
    resp = await client.get(url, headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    return [p["name"] for p in resp.json()["items"]]


async def test_archived_product_hidden_from_active_catalog_but_sale_resolves(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=50, price=10.0)

    # A past sale references the product.
    sale = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Cola", "price": 10.0, "quantity": 2}],
            "payment_method": "cash",
        },
        headers=headers,
    )
    assert sale.status_code == 200, sale.text

    # Archive (soft-delete) it.
    deleted = await client.delete(f"/api/v1/products/{pid}", headers=headers)
    assert deleted.status_code == 200, deleted.text

    # It disappears from the active catalog / POS list ...
    assert "Cola" not in await _list_names(client, token)

    # ... but the historical sale still resolves the product.
    txns = await client.get("/api/v1/pos/transactions", headers=headers)
    assert txns.status_code == 200, txns.text
    assert any("Cola" in (t["items_json"] or "") for t in txns.json()["items"])


async def test_include_archived_surfaces_archived_product(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Juice", quantity=5, price=4.0)

    await client.delete(f"/api/v1/products/{pid}", headers=headers)

    # The default list hides it; opting in surfaces it (so it can be restored).
    assert "Juice" not in await _list_names(client, token)

    resp = await client.get(
        "/api/v1/products/list?include_archived=true", headers=headers
    )
    assert resp.status_code == 200, resp.text
    archived = next(p for p in resp.json()["items"] if p["name"] == "Juice")
    assert archived["is_active"] is False


async def test_restore_reactivates_archived_product(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Milk", quantity=8, price=6.0)

    await client.delete(f"/api/v1/products/{pid}", headers=headers)
    assert "Milk" not in await _list_names(client, token)

    restored = await client.post(
        f"/api/v1/products/{pid}/restore", headers=headers
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["is_active"] is True

    # It reappears in the active catalog / POS list.
    assert "Milk" in await _list_names(client, token)


async def test_restore_is_owner_scoped(client):
    # A merchant cannot restore another merchant's archived product.
    user_a, token_a, client_a = await make_client_account(client)
    _, token_b, _ = await make_client_account(client)
    pid = await add_product(client_a, user_a["id"], name="Bread", quantity=3, price=2.0)
    await client.delete(f"/api/v1/products/{pid}", headers=auth_headers(token_a))

    resp = await client.post(
        f"/api/v1/products/{pid}/restore", headers=auth_headers(token_b)
    )
    assert resp.status_code == 404, resp.text

    # The victim's product is still archived (untouched).
    listed = await client.get(
        "/api/v1/products/list?include_archived=true", headers=auth_headers(token_a)
    )
    bread = next(p for p in listed.json()["items"] if p["name"] == "Bread")
    assert bread["is_active"] is False
