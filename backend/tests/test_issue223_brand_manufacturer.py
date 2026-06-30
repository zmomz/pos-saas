"""ISSUE-223 (M4 Product) — brand / manufacturer.

The next tracer-bullet slice of #223 ("Bundles; brand/manufacturer"): a product
can record its **brand** (the marketing name a shopper recognises, e.g. "Nestlé")
and its **manufacturer** (the legal maker, relevant for pharmacy/electronics
verticals where it differs from the brand). Both are optional free-text catalog
fields that round-trip through the public HTTP API.

Pinned end-to-end:

* create accepts and returns ``brand`` / ``manufacturer``, and they survive into
  the catalog listing (so a merchant can find every SKU of a brand);
* update edits them independently of the rest of the catalog row;
* duplicate clones them onto the new SKU (a new size/flavour of the same brand
  keeps the brand & maker).
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


async def test_create_accepts_and_returns_brand_and_manufacturer(client):
    user, token, client_id = await make_client_account(client)
    product = await _create_product(
        client,
        token,
        name="Panadol 500mg",
        brand="Panadol",
        manufacturer="GSK",
    )

    assert product["brand"] == "Panadol"
    assert product["manufacturer"] == "GSK"

    # The fields survive into the catalog listing.
    listed = next(p for p in await _list(client, token) if p["id"] == product["id"])
    assert listed["brand"] == "Panadol"
    assert listed["manufacturer"] == "GSK"


async def test_create_without_brand_defaults_to_null(client):
    user, token, client_id = await make_client_account(client)
    product = await _create_product(client, token, name="Generic")

    assert product["brand"] is None
    assert product["manufacturer"] is None


async def test_update_edits_brand_and_manufacturer(client):
    user, token, client_id = await make_client_account(client)
    product = await _create_product(client, token, name="TV", brand="Acme")

    resp = await client.put(
        f"/api/v1/products/{product['id']}",
        json={"brand": "Sony", "manufacturer": "Sony Corp"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    updated = resp.json()
    assert updated["brand"] == "Sony"
    assert updated["manufacturer"] == "Sony Corp"


async def test_duplicate_clones_brand_and_manufacturer(client):
    user, token, client_id = await make_client_account(client)
    original = await _create_product(
        client, token, name="Cola 330ml", brand="FizzCo", manufacturer="FizzCo Bottling"
    )

    resp = await client.post(
        f"/api/v1/products/{original['id']}/duplicate", headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    copy = resp.json()

    # A new size/flavour of the same brand keeps the brand & maker.
    assert copy["brand"] == "FizzCo"
    assert copy["manufacturer"] == "FizzCo Bottling"
