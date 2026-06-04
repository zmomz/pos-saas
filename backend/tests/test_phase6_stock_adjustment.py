"""F-036 — stock counts & adjustments with reasons → variance (INV-06).

The product had no way to reconcile on-hand stock against a physical count or record
wastage/damage with a reason — only the deprecated ``POST /inventory/deduct`` mutated
stock with no reason/variance/audit. These tests pin the corrected behavior:

- a ``count`` against a branch sets the per-branch ledger to the counted figure and
  writes a ``stock_adjustments`` variance row (counted − system);
- a ``wastage`` recount that is lower records a negative variance and shrinks stock;
- a client-level adjustment (no branch) updates ``products.quantity``;
- an unknown reason is rejected (400) and nothing is written;
- the endpoint is owner-scoped — a client cannot adjust another client's stock (404).
"""
import pytest
from sqlalchemy import select

from conftest import add_product, auth_headers, make_client_account
from core.database import db_manager
from models.products import Products
from models.stock_adjustments import Stock_adjustments


async def _make_branch(client, headers, name):
    resp = await client.post(
        "/api/v1/entities/branches",
        json={"name": name, "is_active": True},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _allocate(client, headers, branch_id, product_id, quantity):
    resp = await client.put(
        f"/api/v1/pos/branches/{branch_id}/stock",
        json={"product_id": product_id, "quantity": quantity},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text


async def _branch_qty(client, headers, branch_id, product_id):
    resp = await client.get(f"/api/v1/pos/branches/{branch_id}/stock", headers=headers)
    return {i["product_id"]: i["quantity"] for i in resp.json()["items"]}.get(product_id)


@pytest.mark.asyncio
async def test_count_adjustment_sets_branch_stock_and_records_variance(client):
    """A physical count sets the branch ledger to the counted figure + records the gap."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=0, price=10.0)
    branch = await _make_branch(client, headers, "Main")
    await _allocate(client, headers, branch, pid, 50)

    # Counted 47 against a system figure of 50 → variance -3.
    resp = await client.post(
        "/api/v1/production/stock-adjustments",
        json={"product_id": pid, "branch_id": branch, "reason": "count", "counted_quantity": 47},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["system_quantity"] == 50
    assert body["counted_quantity"] == 47
    assert body["variance"] == -3
    assert body["reason"] == "count"

    # The branch ledger now reads the counted figure.
    assert await _branch_qty(client, headers, branch, pid) == 47

    # The variance row was persisted.
    async with db_manager.async_session_maker() as db:
        rows = (
            await db.execute(
                select(Stock_adjustments).where(Stock_adjustments.client_id == client_id)
            )
        ).scalars().all()
    assert len(rows) == 1
    assert rows[0].product_id == pid and rows[0].branch_id == branch
    assert rows[0].variance == -3 and rows[0].reason == "count"


@pytest.mark.asyncio
async def test_wastage_records_negative_variance(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=0, price=10.0)
    branch = await _make_branch(client, headers, "Main")
    await _allocate(client, headers, branch, pid, 20)

    resp = await client.post(
        "/api/v1/production/stock-adjustments",
        json={
            "product_id": pid, "branch_id": branch, "reason": "wastage",
            "counted_quantity": 15, "note": "expired stock",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["reason"] == "wastage" and body["variance"] == -5
    assert body["note"] == "expired stock"
    assert await _branch_qty(client, headers, branch, pid) == 15


@pytest.mark.asyncio
async def test_client_level_adjustment_updates_product_quantity(client):
    """With no branch_id the client-level products.quantity is reconciled."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=8, price=10.0)

    resp = await client.post(
        "/api/v1/production/stock-adjustments",
        json={"product_id": pid, "reason": "correction", "counted_quantity": 12},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["branch_id"] is None
    assert body["system_quantity"] == 8 and body["variance"] == 4

    async with db_manager.async_session_maker() as db:
        qty = (
            await db.execute(select(Products.quantity).where(Products.id == pid))
        ).scalar_one()
    assert qty == 12


@pytest.mark.asyncio
async def test_adjustment_rejects_unknown_reason(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=5, price=10.0)

    resp = await client.post(
        "/api/v1/production/stock-adjustments",
        json={"product_id": pid, "reason": "shrinkage", "counted_quantity": 3},
        headers=headers,
    )
    assert resp.status_code == 400, resp.text

    # Stock untouched and no variance row written (rolled back wholly).
    async with db_manager.async_session_maker() as db:
        qty = (
            await db.execute(select(Products.quantity).where(Products.id == pid))
        ).scalar_one()
        rows = (
            await db.execute(
                select(Stock_adjustments).where(Stock_adjustments.client_id == client_id)
            )
        ).scalars().all()
    assert qty == 5 and len(rows) == 0


@pytest.mark.asyncio
async def test_adjustment_history_listing_is_owner_scoped(client):
    """The variance history lists only the caller's adjustments (SEC-02)."""
    user_a, token_a, client_a = await make_client_account(client)
    headers_a = auth_headers(token_a)
    pid_a = await add_product(client_a, user_a["id"], quantity=10, price=10.0)
    await client.post(
        "/api/v1/production/stock-adjustments",
        json={"product_id": pid_a, "reason": "count", "counted_quantity": 7},
        headers=headers_a,
    )

    # A sees their own variance row.
    listing = await client.get("/api/v1/production/stock-adjustments", headers=headers_a)
    assert listing.status_code == 200, listing.text
    items = listing.json()["items"]
    assert len(items) == 1 and items[0]["product_id"] == pid_a and items[0]["variance"] == -3

    # A second, unrelated client sees none of A's rows.
    _user_b, token_b, _client_b = await make_client_account(client)
    other = await client.get(
        "/api/v1/production/stock-adjustments", headers=auth_headers(token_b)
    )
    assert other.status_code == 200, other.text
    assert other.json()["items"] == []


@pytest.mark.asyncio
async def test_adjustment_is_owner_scoped(client):
    """A client cannot adjust another client's product (SEC-02)."""
    user_a, token_a, client_a = await make_client_account(client)
    pid_a = await add_product(client_a, user_a["id"], quantity=10, price=10.0)

    _user_b, token_b, _client_b = await make_client_account(client)
    headers_b = auth_headers(token_b)
    resp = await client.post(
        "/api/v1/production/stock-adjustments",
        json={"product_id": pid_a, "reason": "count", "counted_quantity": 0},
        headers=headers_b,
    )
    assert resp.status_code == 404, resp.text

    # A's stock is untouched.
    async with db_manager.async_session_maker() as db:
        qty = (
            await db.execute(select(Products.quantity).where(Products.id == pid_a))
        ).scalar_one()
    assert qty == 10
