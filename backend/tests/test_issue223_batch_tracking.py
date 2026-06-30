"""ISSUE-223 (M4 Product) — batch/expiry tracking enforced at sale.

The next tracer-bullet slice of #223 ("Batch/expiry/serial/IMEI tracking ...
enforced at sale") after serial/IMEI: a product can be flagged **batch-tracked**
(``track_batch``) — a lot-controlled good such as a medicine, food item or any
perishable whose dispensed lot (and its expiry) must be recorded at the point of
sale. Such a product cannot be rung up without capturing a batch/lot number; the
server is authoritative and rejects a tracked line that arrives without one.

Pinned end-to-end:

* create accepts and returns ``track_batch``, and it survives into the catalog
  listing; absent it defaults to ``False``;
* update toggles ``track_batch`` independently of the rest of the catalog row;
* duplicate clones ``track_batch`` onto the new SKU;
* selling a batch-tracked product WITHOUT a batch number is rejected (400),
  WITH one it succeeds — while an ordinary (untracked) product sells with no
  batch number.
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


async def _sale(client, token, item):
    body = {"items": [item], "payment_method": "cash"}
    return await client.post(
        "/api/v1/pos/transaction", json=body, headers=auth_headers(token)
    )


async def test_create_accepts_and_returns_track_batch(client):
    user, token, client_id = await make_client_account(client)
    product = await _create_product(
        client, token, name="Amoxicillin 500mg", track_batch=True
    )

    assert product["track_batch"] is True

    # The flag survives into the catalog listing.
    listed = next(p for p in await _list(client, token) if p["id"] == product["id"])
    assert listed["track_batch"] is True


async def test_create_without_track_batch_defaults_to_false(client):
    user, token, client_id = await make_client_account(client)
    product = await _create_product(client, token, name="Notebook")

    assert product["track_batch"] is False


async def test_update_toggles_track_batch(client):
    user, token, client_id = await make_client_account(client)
    product = await _create_product(client, token, name="Paracetamol")

    resp = await client.put(
        f"/api/v1/products/{product['id']}",
        json={"track_batch": True},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["track_batch"] is True


async def test_duplicate_clones_track_batch(client):
    user, token, client_id = await make_client_account(client)
    original = await _create_product(
        client, token, name="Insulin", track_batch=True
    )

    resp = await client.post(
        f"/api/v1/products/{original['id']}/duplicate", headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["track_batch"] is True


async def test_sale_of_batch_tracked_product_without_batch_is_rejected(client):
    user, token, client_id = await make_client_account(client)
    product = await _create_product(
        client, token, name="Ibuprofen", price=20.0, quantity=50, track_batch=True
    )

    resp = await _sale(
        client,
        token,
        {"product_id": product["id"], "name": "Ibuprofen", "price": 20.0, "quantity": 1},
    )
    assert resp.status_code == 400, resp.text
    assert "batch" in resp.json()["detail"].lower()


async def test_sale_of_batch_tracked_product_with_batch_succeeds(client):
    user, token, client_id = await make_client_account(client)
    product = await _create_product(
        client, token, name="Ibuprofen", price=20.0, quantity=50, track_batch=True
    )

    resp = await _sale(
        client,
        token,
        {
            "product_id": product["id"],
            "name": "Ibuprofen",
            "price": 20.0,
            "quantity": 1,
            "batch_number": "LOT-2026-04-A",
        },
    )
    assert resp.status_code == 200, resp.text


async def test_sale_of_untracked_product_needs_no_batch(client):
    user, token, client_id = await make_client_account(client)
    product = await _create_product(
        client, token, name="USB cable", price=15.0, quantity=10
    )

    resp = await _sale(
        client,
        token,
        {"product_id": product["id"], "name": "USB cable", "price": 15.0, "quantity": 1},
    )
    assert resp.status_code == 200, resp.text
