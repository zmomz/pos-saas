"""F-035 — reorder points → reorder-based low-stock + auto-PO suggestion (INV-08).

Low-stock used to be a fixed ``?threshold=`` for every product. These tests pin
the corrected behavior:

- a product carries a per-product ``reorder_point`` (and ``reorder_quantity``)
  round-tripped through create/response;
- ``GET /products/low-stock`` flags a product when on-hand <= its reorder_point;
- a product above its reorder point is not flagged;
- a product with no reorder point falls back to the legacy fixed threshold;
- ``GET /products/reorder-suggestions`` returns at/below-point products with a
  suggested order quantity (the auto-PO surface), opt-in per product;
- both endpoints are owner-scoped — a client never sees another client's stock.
"""
import pytest

from conftest import auth_headers, make_client_account


async def _create_product(client, headers, name, quantity, reorder_point=0, reorder_quantity=0):
    resp = await client.post(
        "/api/v1/products/create",
        json={
            "name": name,
            "price": 10.0,
            "quantity": quantity,
            "reorder_point": reorder_point,
            "reorder_quantity": reorder_quantity,
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _low_stock_ids(client, headers):
    resp = await client.get("/api/v1/products/low-stock", headers=headers)
    assert resp.status_code == 200, resp.text
    return {i["id"] for i in resp.json()["items"]}


@pytest.mark.asyncio
async def test_create_product_round_trips_reorder_fields(client):
    user, token, _ = await make_client_account(client)
    headers = auth_headers(token)
    body = await _create_product(client, headers, "Coffee", quantity=8, reorder_point=10, reorder_quantity=50)
    assert body["reorder_point"] == 10
    assert body["reorder_quantity"] == 50


@pytest.mark.asyncio
async def test_reorder_point_flags_low_stock_when_at_or_below(client):
    """on-hand <= reorder_point → low-stock; above → not, regardless of the fixed 10."""
    user, token, _ = await make_client_account(client)
    headers = auth_headers(token)

    # reorder_point 20 (> the legacy threshold of 10), on-hand 15 → low because 15 <= 20.
    low = await _create_product(client, headers, "Low", quantity=15, reorder_point=20)
    # reorder_point 5, on-hand 8 → NOT low (8 > 5) even though 8 < the legacy 10.
    high = await _create_product(client, headers, "High", quantity=8, reorder_point=5)

    ids = await _low_stock_ids(client, headers)
    assert low["id"] in ids
    assert high["id"] not in ids


@pytest.mark.asyncio
async def test_legacy_threshold_used_without_reorder_point(client):
    """A product with no reorder point falls back to the fixed default threshold (10)."""
    user, token, _ = await make_client_account(client)
    headers = auth_headers(token)

    below = await _create_product(client, headers, "Below", quantity=8, reorder_point=0)
    above = await _create_product(client, headers, "Above", quantity=12, reorder_point=0)

    ids = await _low_stock_ids(client, headers)
    assert below["id"] in ids
    assert above["id"] not in ids


@pytest.mark.asyncio
async def test_reorder_suggestions_proposes_order_quantity(client):
    """At/below-point products surface with a suggested order quantity (auto-PO)."""
    user, token, _ = await make_client_account(client)
    headers = auth_headers(token)

    triggered = await _create_product(
        client, headers, "Triggered", quantity=8, reorder_point=10, reorder_quantity=50
    )
    # Above its reorder point → no suggestion.
    ok = await _create_product(client, headers, "Stocked", quantity=30, reorder_point=10, reorder_quantity=50)
    # Low but with NO reorder point → not in the opt-in auto-PO surface.
    no_point = await _create_product(client, headers, "NoPoint", quantity=2, reorder_point=0)

    resp = await client.get("/api/v1/products/reorder-suggestions", headers=headers)
    assert resp.status_code == 200, resp.text
    by_id = {i["product_id"]: i for i in resp.json()["items"]}

    assert triggered["id"] in by_id
    assert by_id[triggered["id"]]["suggested_order_quantity"] == 50
    assert by_id[triggered["id"]]["on_hand"] == 8
    assert by_id[triggered["id"]]["reorder_point"] == 10
    assert ok["id"] not in by_id
    assert no_point["id"] not in by_id


@pytest.mark.asyncio
async def test_suggestion_without_explicit_quantity_brings_above_point(client):
    """No reorder_quantity → suggest enough to climb back above the reorder point."""
    user, token, _ = await make_client_account(client)
    headers = auth_headers(token)
    p = await _create_product(client, headers, "Defaulted", quantity=3, reorder_point=10)

    resp = await client.get("/api/v1/products/reorder-suggestions", headers=headers)
    by_id = {i["product_id"]: i for i in resp.json()["items"]}
    # 10 - 3 + 1 = 8 units → lands the product above its reorder point.
    assert by_id[p["id"]]["suggested_order_quantity"] == 8


@pytest.mark.asyncio
async def test_reorder_endpoints_are_owner_scoped(client):
    """A client never sees another client's low-stock or reorder suggestions (SEC-02)."""
    user_a, token_a, _ = await make_client_account(client)
    headers_a = auth_headers(token_a)
    a_prod = await _create_product(
        client, headers_a, "A-Item", quantity=1, reorder_point=10, reorder_quantity=20
    )

    user_b, token_b, _ = await make_client_account(client)
    headers_b = auth_headers(token_b)

    # Client B's low-stock and suggestions must not include client A's product.
    assert a_prod["id"] not in await _low_stock_ids(client, headers_b)
    resp_b = await client.get("/api/v1/products/reorder-suggestions", headers=headers_b)
    assert a_prod["id"] not in {i["product_id"] for i in resp_b.json()["items"]}
