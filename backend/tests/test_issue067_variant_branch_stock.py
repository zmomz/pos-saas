"""ISSUE-067 — Per-branch variant stock (INV-03 × INV-04).

A product *variant* (size/colour SKU) carries its stock per **branch**, not just a
single client-level total: a branch-tagged variant sale draws from that branch's
variant ledger, so a sale in branch A never touches branch B's level nor the
variant's client-level façade quantity.
"""
import pytest
from sqlalchemy import select

from conftest import add_product, auth_headers, make_client_account
from core.database import db_manager
from models.product_variants import Product_variants


async def _make_branch(client, headers, name):
    resp = await client.post(
        "/api/v1/entities/branches",
        json={"name": name, "is_active": True},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


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


async def _set_variant_stock(client, headers, branch_id, variant_id, qty):
    resp = await client.put(
        f"/api/v1/pos/branches/{branch_id}/variant-stock",
        json={"variant_id": variant_id, "quantity": qty},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _branch_variant_qty(client, headers, branch_id, variant_id):
    resp = await client.get(
        f"/api/v1/pos/branches/{branch_id}/variant-stock", headers=headers
    )
    assert resp.status_code == 200, resp.text
    return {i["variant_id"]: i["quantity"] for i in resp.json()["items"]}.get(variant_id)


async def _global_variant_qty(variant_id: int) -> int:
    async with db_manager.async_session_maker() as db:
        return (
            await db.execute(
                select(Product_variants.quantity).where(Product_variants.id == variant_id)
            )
        ).scalar_one()


@pytest.mark.asyncio
async def test_branch_variant_sale_deducts_only_that_branch(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="T-Shirt", quantity=0, price=50.0)
    red = await _make_variant(
        client, headers, product_id=pid, client_id=client_id,
        name="Red / Large", barcode="ISS67-RED-L", price=55.0, quantity=8,
    )

    branch_a = await _make_branch(client, headers, "Branch A")
    branch_b = await _make_branch(client, headers, "Branch B")
    await _set_variant_stock(client, headers, branch_a, red, 10)
    await _set_variant_stock(client, headers, branch_b, red, 20)

    # Sell 3 of the variant in branch A.
    resp = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{
                "product_id": pid,
                "variant_id": red,
                "name": "Red / Large",
                "price": 55.0,
                "quantity": 3,
            }],
            "payment_method": "cash",
            "branch_id": branch_a,
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    # Branch A down to 7; Branch B unchanged at 20.
    assert await _branch_variant_qty(client, headers, branch_a, red) == 7
    assert await _branch_variant_qty(client, headers, branch_b, red) == 20
    # Client-level variant façade quantity is untouched by a branch-tagged sale.
    assert await _global_variant_qty(red) == 8


@pytest.mark.asyncio
async def test_branch_variant_insufficient_stock_rejected(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Mug", quantity=0, price=10.0)
    v = await _make_variant(
        client, headers, product_id=pid, client_id=client_id,
        name="Small", barcode="ISS67-MUG-S", price=10.0, quantity=50,
    )
    branch_a = await _make_branch(client, headers, "Branch A")
    await _set_variant_stock(client, headers, branch_a, v, 2)

    resp = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{
                "product_id": pid,
                "variant_id": v,
                "name": "Small",
                "price": 10.0,
                "quantity": 5,
            }],
            "payment_method": "cash",
            "branch_id": branch_a,
        },
        headers=headers,
    )
    assert resp.status_code == 400, resp.text
    # Branch ledger unchanged after the rejected sale (rolled back).
    assert await _branch_variant_qty(client, headers, branch_a, v) == 2


@pytest.mark.asyncio
async def test_void_restores_branch_variant_stock(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Cap", quantity=0, price=20.0)
    v = await _make_variant(
        client, headers, product_id=pid, client_id=client_id,
        name="Black", barcode="ISS67-CAP-BLK", price=20.0, quantity=99,
    )
    branch_a = await _make_branch(client, headers, "Branch A")
    await _set_variant_stock(client, headers, branch_a, v, 5)

    sale = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{
                "product_id": pid,
                "variant_id": v,
                "name": "Black",
                "price": 20.0,
                "quantity": 2,
            }],
            "payment_method": "cash",
            "branch_id": branch_a,
        },
        headers=headers,
    )
    assert sale.status_code == 200, sale.text
    assert await _branch_variant_qty(client, headers, branch_a, v) == 3  # 5 - 2

    txn_id = sale.json()["id"]
    void = await client.post(f"/api/v1/pos/transactions/{txn_id}/void", json={}, headers=headers)
    assert void.status_code == 200, void.text
    assert void.json()["status"] == "voided"
    assert await _branch_variant_qty(client, headers, branch_a, v) == 5  # restored
