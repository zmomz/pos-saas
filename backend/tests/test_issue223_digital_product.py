"""ISSUE-223 (M4 Product) — digital products.

The next tracer-bullet slice of #223 ("Batch/expiry/serial/IMEI tracking; digital
products"): a product can be flagged **digital** (``is_digital``) — an e-voucher,
top-up, licence or download that has no physical stock. Because there is no
on-hand inventory to deplete, a digital product can never be "low" and is never an
auto-reorder candidate, so it is excluded from the low-stock list and the
reorder-suggestions surface even when its on-hand sits at/below a reorder point.

Pinned end-to-end:

* create accepts and returns ``is_digital``, and it survives into the catalog
  listing; absent it defaults to ``False``;
* update toggles ``is_digital`` independently of the rest of the catalog row;
* duplicate clones ``is_digital`` onto the new SKU;
* a digital product at/below its reorder point is excluded from BOTH the
  low-stock list and the reorder-suggestions surface (no physical stock to run
  out of), while a physical product in the same state still appears.
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


async def test_create_accepts_and_returns_is_digital(client):
    user, token, client_id = await make_client_account(client)
    product = await _create_product(
        client, token, name="Gift Card 50", is_digital=True
    )

    assert product["is_digital"] is True

    # The flag survives into the catalog listing.
    listed = next(p for p in await _list(client, token) if p["id"] == product["id"])
    assert listed["is_digital"] is True


async def test_create_without_is_digital_defaults_to_false(client):
    user, token, client_id = await make_client_account(client)
    product = await _create_product(client, token, name="Bottle of water")

    assert product["is_digital"] is False


async def test_update_toggles_is_digital(client):
    user, token, client_id = await make_client_account(client)
    product = await _create_product(client, token, name="Voucher")

    resp = await client.put(
        f"/api/v1/products/{product['id']}",
        json={"is_digital": True},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_digital"] is True


async def test_duplicate_clones_is_digital(client):
    user, token, client_id = await make_client_account(client)
    original = await _create_product(
        client, token, name="Mobile top-up", is_digital=True
    )

    resp = await client.post(
        f"/api/v1/products/{original['id']}/duplicate", headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_digital"] is True


async def test_digital_product_excluded_from_low_stock(client):
    user, token, client_id = await make_client_account(client)
    # Both sit at/below their reorder point, but only the physical one can be low.
    physical = await _create_product(
        client, token, name="Cola can", quantity=0, reorder_point=5
    )
    digital = await _create_product(
        client, token, name="E-voucher", quantity=0, reorder_point=5, is_digital=True
    )

    resp = await client.get(
        "/api/v1/products/low-stock", headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    low_ids = {p["id"] for p in resp.json()["items"]}

    assert physical["id"] in low_ids
    assert digital["id"] not in low_ids


async def test_digital_product_excluded_from_reorder_suggestions(client):
    user, token, client_id = await make_client_account(client)
    physical = await _create_product(
        client, token, name="Printer paper", quantity=1, reorder_point=10
    )
    digital = await _create_product(
        client, token, name="Software licence", quantity=1, reorder_point=10, is_digital=True
    )

    resp = await client.get(
        "/api/v1/products/reorder-suggestions", headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    suggested_ids = {s["product_id"] for s in resp.json()["items"]}

    assert physical["id"] in suggested_ids
    assert digital["id"] not in suggested_ids
