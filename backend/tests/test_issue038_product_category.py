"""ISSUE-038 (H7) — product↔category linkage.

Products historically carried a free-text ``category`` string with no link to the
merchant's category tree. These tests pin the new ``category_id`` FK behaviour:
a product can be assigned a *real* owner-scoped category at create/edit time, the
listing can be filtered by that linked category, and a foreign category id is
rejected. Exercised end-to-end through the public HTTP API.
"""
from conftest import auth_headers, make_client_account


async def _make_category(client, token, name: str) -> int:
    resp = await client.post(
        "/api/v1/entities/categories",
        json={"name": name},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_create_product_assigns_real_category(client):
    _, token, _ = await make_client_account(client)
    cat_id = await _make_category(client, token, "Beverages")

    resp = await client.post(
        "/api/v1/products/create",
        json={"name": "Cola", "price": 5.0, "quantity": 10, "category_id": cat_id},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["category_id"] == cat_id
    # The linked category's name is denormalised for display continuity.
    assert body["category"] == "Beverages"


async def test_list_filters_by_linked_category(client):
    _, token, _ = await make_client_account(client)
    drinks = await _make_category(client, token, "Drinks")
    snacks = await _make_category(client, token, "Snacks")

    for name, cat in [("Cola", drinks), ("Water", drinks), ("Chips", snacks)]:
        resp = await client.post(
            "/api/v1/products/create",
            json={"name": name, "price": 3.0, "quantity": 5, "category_id": cat},
            headers=auth_headers(token),
        )
        assert resp.status_code == 200, resp.text

    listed = await client.get(
        f"/api/v1/products/list?category_id={drinks}",
        headers=auth_headers(token),
    )
    assert listed.status_code == 200, listed.text
    body = listed.json()
    names = sorted(p["name"] for p in body["items"])
    assert names == ["Cola", "Water"]
    assert all(p["category_id"] == drinks for p in body["items"])


async def test_update_reassigns_linked_category(client):
    _, token, _ = await make_client_account(client)
    old = await _make_category(client, token, "Old")
    new = await _make_category(client, token, "New")

    created = await client.post(
        "/api/v1/products/create",
        json={"name": "Item", "price": 1.0, "quantity": 1, "category_id": old},
        headers=auth_headers(token),
    )
    product_id = created.json()["id"]

    updated = await client.put(
        f"/api/v1/products/{product_id}",
        json={"category_id": new},
        headers=auth_headers(token),
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["category_id"] == new
    assert body["category"] == "New"


async def test_create_rejects_foreign_category(client):
    # A merchant cannot link a product to another merchant's category.
    _, token_a, _ = await make_client_account(client)
    _, token_b, _ = await make_client_account(client)
    foreign = await _make_category(client, token_b, "TheirCategory")

    resp = await client.post(
        "/api/v1/products/create",
        json={"name": "Sneaky", "price": 1.0, "quantity": 1, "category_id": foreign},
        headers=auth_headers(token_a),
    )
    assert resp.status_code == 400, resp.text
