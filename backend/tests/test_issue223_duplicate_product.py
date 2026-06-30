"""ISSUE-223 (M4 Product) — duplicate a product.

The first tracer-bullet slice of #223 ("Products can be duplicated/archived/
restored"): archive/restore already ship (ISSUE-068); this adds *duplicate*. A
merchant clones an existing SKU to seed a similar one (a new size, flavour, or
variant) without re-keying every catalog field.

Pinned end-to-end through the public HTTP API:

* duplicating copies the catalog fields onto a brand-new active product (new id),
  with the name marked as a copy, and leaves the original untouched;
* the clone is a *fresh* SKU — zero on-hand stock and no barcode (a barcode is a
  unique physical scan code; the merchant assigns a new one) — so it never
  collides with the original at the scanner;
* duplicate is owner-scoped: a merchant cannot duplicate another merchant's
  product (404).
"""
from conftest import auth_headers, make_client_account


async def _create_product(client, token, **fields):
    payload = {"name": "Widget", "price": 10.0}
    payload.update(fields)
    resp = await client.post(
        "/api/v1/products/create", json=payload, headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _list(client, token, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    url = "/api/v1/products/list" + (f"?{query}" if query else "")
    resp = await client.get(url, headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    return resp.json()["items"]


async def test_duplicate_clones_catalog_fields_into_new_active_product(client):
    user, token, client_id = await make_client_account(client)
    original = await _create_product(
        client,
        token,
        name="Espresso Beans",
        name_ar="حبوب اسبريسو",
        price=42.5,
        cost_price=20.0,
        category="Coffee",
        vat_rate=15.0,
        is_weighted=True,
        unit_label="kg",
    )

    resp = await client.post(
        f"/api/v1/products/{original['id']}/duplicate", headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    copy = resp.json()

    # A brand-new product (distinct id), active, name marked as a copy.
    assert copy["id"] != original["id"]
    assert copy["is_active"] is True
    assert copy["name"] == "Espresso Beans (Copy)"

    # Catalog fields are carried over.
    assert copy["name_ar"] == "حبوب اسبريسو"
    assert copy["price"] == 42.5
    assert copy["cost_price"] == 20.0
    assert copy["category"] == "Coffee"
    assert copy["vat_rate"] == 15.0
    assert copy["is_weighted"] is True
    assert copy["unit_label"] == "kg"

    # Both the original and the copy are in the active catalog.
    names = [p["name"] for p in await _list(client, token)]
    assert "Espresso Beans" in names
    assert "Espresso Beans (Copy)" in names


async def test_duplicate_is_a_fresh_sku_no_stock_no_barcode(client):
    user, token, client_id = await make_client_account(client)
    original = await _create_product(
        client, token, name="Cola", price=5.0, quantity=99, barcode="1234567890123"
    )

    resp = await client.post(
        f"/api/v1/products/{original['id']}/duplicate", headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    copy = resp.json()

    # A fresh SKU: no inherited stock and no colliding barcode.
    assert copy["quantity"] == 0
    assert copy["barcode"] is None

    # The original is untouched (stock + barcode intact).
    assert original["quantity"] == 99
    assert original["barcode"] == "1234567890123"


async def test_duplicate_is_owner_scoped(client):
    # A merchant cannot duplicate another merchant's product.
    user_a, token_a, client_a = await make_client_account(client)
    _, token_b, _ = await make_client_account(client)
    original = await _create_product(client, token_a, name="Bread", price=2.0)

    resp = await client.post(
        f"/api/v1/products/{original['id']}/duplicate", headers=auth_headers(token_b)
    )
    assert resp.status_code == 404, resp.text

    # The victim's catalog gained nothing.
    names = [p["name"] for p in await _list(client, token_a)]
    assert names.count("Bread") == 1
    assert not any(n == "Bread (Copy)" for n in names)
