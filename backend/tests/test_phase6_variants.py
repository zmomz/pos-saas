"""Phase 6 — product variants / matrix (INV-04, F-033).

A product can expose several **variants** (size/colour), each a sellable SKU with
its own barcode, price and stock. The POS resolves a scanned variant barcode to
the variant and decrements *that variant's* stock independently of its siblings.

Catches forever (per the COMPLETENESS_REVIEW F-033 finding):
* a 2-variant product exposes 2 scannable barcodes that resolve to distinct SKUs;
* selling one variant decrements that variant's stock and leaves the sibling
  variant — and the parent product's quantity — untouched (independent stock);
* a variant sale over the variant's stock is rejected (400);
* voiding a variant sale restores the variant's stock;
* variants are owner-scoped (one client can't read/resolve another's variants).
"""
import pytest
from sqlalchemy import select

from conftest import add_product, auth_headers, make_client_account, get_product_quantity
from core.database import db_manager
from models.product_variants import Product_variants


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _make_variant(client, headers, *, product_id, client_id, name, barcode, price, quantity):
    resp = await client.post(
        "/api/v1/entities/product_variants",
        json={
            "client_id": client_id,
            "product_id": product_id,
            "name": name,
            "barcode": barcode,
            "price": price,
            "quantity": quantity,
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _variant_qty(variant_id: int) -> int:
    async with db_manager.async_session_maker() as db:
        return (
            await db.execute(
                select(Product_variants.quantity).where(Product_variants.id == variant_id)
            )
        ).scalar_one()


async def _sell_variant(client, headers, *, product_id, variant_id, name, price, qty):
    resp = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{
                "product_id": product_id,
                "variant_id": variant_id,
                "name": name,
                "price": price,
                "quantity": qty,
            }],
            "payment_method": "cash",
        },
        headers=headers,
    )
    return resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_two_variants_resolve_to_distinct_scannable_skus(client):
    """A 2-variant product exposes 2 barcodes that resolve to distinct SKUs."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="T-Shirt", quantity=0, price=50.0)
    red = await _make_variant(
        client, headers, product_id=pid, client_id=client_id,
        name="Red / Large", barcode="TSHIRT-RED-L", price=55.0, quantity=8,
    )
    blue = await _make_variant(
        client, headers, product_id=pid, client_id=client_id,
        name="Blue / Small", barcode="TSHIRT-BLU-S", price=52.0, quantity=3,
    )

    r1 = await client.get("/api/v1/pos/resolve-barcode?barcode=TSHIRT-RED-L", headers=headers)
    r2 = await client.get("/api/v1/pos/resolve-barcode?barcode=TSHIRT-BLU-S", headers=headers)
    assert r1.status_code == 200 and r2.status_code == 200, (r1.text, r2.text)
    b1, b2 = r1.json(), r2.json()
    assert b1["kind"] == "variant" and b1["variant_id"] == red and b1["product_id"] == pid
    assert b1["price"] == 55.0
    assert b2["kind"] == "variant" and b2["variant_id"] == blue
    assert b1["variant_id"] != b2["variant_id"]


@pytest.mark.asyncio
async def test_variant_sale_decrements_variant_stock_independently(client):
    """Selling one variant decrements that variant only — sibling + parent untouched."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="T-Shirt", quantity=20, price=50.0)
    red = await _make_variant(
        client, headers, product_id=pid, client_id=client_id,
        name="Red / Large", barcode="V-RED", price=55.0, quantity=8,
    )
    blue = await _make_variant(
        client, headers, product_id=pid, client_id=client_id,
        name="Blue / Small", barcode="V-BLUE", price=52.0, quantity=3,
    )

    resp = await _sell_variant(
        client, headers, product_id=pid, variant_id=red, name="Red / Large", price=55.0, qty=2,
    )
    assert resp.status_code == 200, resp.text

    assert await _variant_qty(red) == 6     # 8 - 2
    assert await _variant_qty(blue) == 3     # sibling untouched
    assert await get_product_quantity(pid) == 20  # parent aggregate untouched


@pytest.mark.asyncio
async def test_variant_sale_over_stock_rejected(client):
    """A variant sale exceeding the variant's stock is rejected and persists nothing."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Mug", quantity=0, price=10.0)
    v = await _make_variant(
        client, headers, product_id=pid, client_id=client_id,
        name="Small", barcode="MUG-S", price=10.0, quantity=1,
    )

    resp = await _sell_variant(
        client, headers, product_id=pid, variant_id=v, name="Small", price=10.0, qty=5,
    )
    assert resp.status_code == 400, resp.text
    assert await _variant_qty(v) == 1  # nothing deducted (rolled back)


@pytest.mark.asyncio
async def test_void_restores_variant_stock(client):
    """Voiding a variant sale credits the variant's stock back."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Cap", quantity=0, price=20.0)
    v = await _make_variant(
        client, headers, product_id=pid, client_id=client_id,
        name="Black", barcode="CAP-BLK", price=20.0, quantity=5,
    )

    sale = await _sell_variant(
        client, headers, product_id=pid, variant_id=v, name="Black", price=20.0, qty=2,
    )
    assert sale.status_code == 200, sale.text
    assert await _variant_qty(v) == 3

    txn_id = sale.json()["id"]
    void = await client.post(f"/api/v1/pos/transactions/{txn_id}/void", json={}, headers=headers)
    assert void.status_code == 200, void.text
    assert void.json()["status"] == "voided"
    assert await _variant_qty(v) == 5  # restored


@pytest.mark.asyncio
async def test_variants_are_owner_scoped(client):
    """A client cannot read or resolve another client's variants (SEC-02)."""
    user_a, token_a, client_a = await make_client_account(client)
    headers_a = auth_headers(token_a)
    pid_a = await add_product(client_a, user_a["id"], name="A-Shirt", quantity=0, price=50.0)
    var_a = await _make_variant(
        client, headers_a, product_id=pid_a, client_id=client_a,
        name="Red", barcode="A-ONLY-BARCODE", price=55.0, quantity=8,
    )

    _user_b, token_b, _client_b = await make_client_account(client)
    headers_b = auth_headers(token_b)

    # B cannot fetch A's variant by id …
    got = await client.get(f"/api/v1/entities/product_variants/{var_a}", headers=headers_b)
    assert got.status_code == 404, got.text
    # … nor resolve A's barcode against B's own (empty) catalog.
    res = await client.get(
        "/api/v1/pos/resolve-barcode?barcode=A-ONLY-BARCODE", headers=headers_b
    )
    assert res.status_code == 200 and res.json()["kind"] == "none", res.text
