"""ISSUE-223 (M4 Product) — serial/IMEI tracking enforced at sale.

The next tracer-bullet slice of #223 ("Batch/expiry/serial/IMEI tracking ...
enforced at sale"): a product can be flagged **serial-tracked**
(``track_serial``) — a serialised good such as a phone (IMEI), appliance or any
warranty-tracked item. Such a product cannot be rung up without capturing a
serial number at the point of sale; the server is authoritative and rejects a
tracked line that arrives with no serial.

Pinned end-to-end:

* create accepts and returns ``track_serial``, and it survives into the catalog
  listing; absent it defaults to ``False``;
* update toggles ``track_serial`` independently of the rest of the catalog row;
* duplicate clones ``track_serial`` onto the new SKU;
* selling a serial-tracked product WITHOUT a serial number is rejected (400),
  WITH one it succeeds — while an ordinary (untracked) product sells with no
  serial.
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


async def test_create_accepts_and_returns_track_serial(client):
    user, token, client_id = await make_client_account(client)
    product = await _create_product(
        client, token, name="iPhone 15", track_serial=True
    )

    assert product["track_serial"] is True

    # The flag survives into the catalog listing.
    listed = next(p for p in await _list(client, token) if p["id"] == product["id"])
    assert listed["track_serial"] is True


async def test_create_without_track_serial_defaults_to_false(client):
    user, token, client_id = await make_client_account(client)
    product = await _create_product(client, token, name="Notebook")

    assert product["track_serial"] is False


async def test_update_toggles_track_serial(client):
    user, token, client_id = await make_client_account(client)
    product = await _create_product(client, token, name="Laptop")

    resp = await client.put(
        f"/api/v1/products/{product['id']}",
        json={"track_serial": True},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["track_serial"] is True


async def test_duplicate_clones_track_serial(client):
    user, token, client_id = await make_client_account(client)
    original = await _create_product(
        client, token, name="Galaxy S24", track_serial=True
    )

    resp = await client.post(
        f"/api/v1/products/{original['id']}/duplicate", headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["track_serial"] is True


async def test_sale_of_serial_tracked_product_without_serial_is_rejected(client):
    user, token, client_id = await make_client_account(client)
    product = await _create_product(
        client, token, name="Pixel 8", price=2000.0, quantity=5, track_serial=True
    )

    resp = await _sale(
        client,
        token,
        {"product_id": product["id"], "name": "Pixel 8", "price": 2000.0, "quantity": 1},
    )
    assert resp.status_code == 400, resp.text
    assert "serial" in resp.json()["detail"].lower()


async def test_sale_of_serial_tracked_product_with_serial_succeeds(client):
    user, token, client_id = await make_client_account(client)
    product = await _create_product(
        client, token, name="Pixel 8", price=2000.0, quantity=5, track_serial=True
    )

    resp = await _sale(
        client,
        token,
        {
            "product_id": product["id"],
            "name": "Pixel 8",
            "price": 2000.0,
            "quantity": 1,
            "serial_number": "IMEI-353915090000001",
        },
    )
    assert resp.status_code == 200, resp.text


async def test_sale_of_untracked_product_needs_no_serial(client):
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
