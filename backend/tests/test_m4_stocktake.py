"""M4 / #207 — guided stocktake (start/freeze/count/variance/approve, resumable).

A sessioned physical count layered on the ``stock_adjustments`` variance primitive
(INV-06). These tests pin the guided flow:

- a session freezes the on-hand baseline across the branch into per-product lines;
- barcode/manual counts fill the lines and compute variance against the frozen figure;
- a draft/frozen session persists (resumable) — counts survive a re-fetch;
- approval posts one ``stock_adjustments`` row per counted line and sets each pool to
  its counted figure, all atomically; a double-approve never double-posts;
- counting before freeze is rejected, and uncounted lines leave stock untouched;
- everything is owner-scoped — a client cannot see/drive another client's stocktake.
"""
import pytest
from sqlalchemy import select, update

from conftest import add_product, auth_headers, make_client_account
from core.database import db_manager
from models.products import Products
from models.stock_adjustments import Stock_adjustments
from models.stock_counts import Stock_count_sessions


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


async def _set_barcode(product_id, barcode):
    async with db_manager.async_session_maker() as db:
        await db.execute(
            update(Products).where(Products.id == product_id).values(barcode=barcode)
        )
        await db.commit()


@pytest.mark.asyncio
async def test_guided_stocktake_happy_path(client):
    """Start → freeze → count → variance → approve posts adjustments + sets stock."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    p1 = await add_product(client_id, user["id"], name="Apples", quantity=0, price=2.0)
    p2 = await add_product(client_id, user["id"], name="Bananas", quantity=0, price=3.0)
    branch = await _make_branch(client, headers, "Main")
    await _allocate(client, headers, branch, p1, 50)
    await _allocate(client, headers, branch, p2, 20)

    # Start a resumable draft.
    resp = await client.post(
        "/api/v1/production/stock-counts",
        json={"branch_id": branch, "name": "Month-end"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    session = resp.json()
    assert session["status"] == "draft"
    sid = session["id"]

    # Freeze: snapshot every active product into a line.
    resp = await client.post(
        f"/api/v1/production/stock-counts/{sid}/freeze", headers=headers
    )
    assert resp.status_code == 200, resp.text
    frozen = resp.json()
    assert frozen["status"] == "frozen"
    assert frozen["line_count"] == 2
    by_pid = {line["product_id"]: line for line in frozen["lines"]}
    assert by_pid[p1]["system_quantity"] == 50
    assert by_pid[p2]["system_quantity"] == 20
    assert by_pid[p1]["counted"] is False

    # Count: 47 apples (short 3), 20 bananas (exact).
    resp = await client.post(
        f"/api/v1/production/stock-counts/{sid}/count",
        json={"product_id": p1, "counted_quantity": 47},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["variance"] == -3
    resp = await client.post(
        f"/api/v1/production/stock-counts/{sid}/count",
        json={"product_id": p2, "counted_quantity": 20},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["variance"] == 0

    # Variance review reflects the persisted counts.
    resp = await client.get(f"/api/v1/production/stock-counts/{sid}", headers=headers)
    review = resp.json()
    assert review["counted_count"] == 2
    assert review["variance_count"] == 1
    assert review["total_variance"] == -3

    # Approve: posts adjustments atomically and sets the ledger.
    resp = await client.post(
        f"/api/v1/production/stock-counts/{sid}/approve", headers=headers
    )
    assert resp.status_code == 200, resp.text
    approved = resp.json()
    assert approved["status"] == "approved"
    assert approved["adjustments_posted"] == 2
    assert approved["total_variance"] == -3

    # The branch ledger now reads the counted figures.
    assert await _branch_qty(client, headers, branch, p1) == 47
    assert await _branch_qty(client, headers, branch, p2) == 20

    # One variance row per counted line was posted.
    async with db_manager.async_session_maker() as db:
        rows = (
            await db.execute(
                select(Stock_adjustments).where(Stock_adjustments.client_id == client_id)
            )
        ).scalars().all()
    assert len(rows) == 2
    assert {r.product_id: r.variance for r in rows} == {p1: -3, p2: 0}
    assert all(r.reason == "count" for r in rows)


@pytest.mark.asyncio
async def test_count_rejected_before_freeze(client):
    """A draft session does not accept counts — it must be frozen first."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=10)
    branch = await _make_branch(client, headers, "Main")
    await _allocate(client, headers, branch, pid, 10)

    resp = await client.post(
        "/api/v1/production/stock-counts", json={"branch_id": branch}, headers=headers
    )
    sid = resp.json()["id"]

    resp = await client.post(
        f"/api/v1/production/stock-counts/{sid}/count",
        json={"product_id": pid, "counted_quantity": 8},
        headers=headers,
    )
    assert resp.status_code == 409, resp.text


@pytest.mark.asyncio
async def test_uncounted_lines_leave_stock_untouched(client):
    """Approving a count where a product was never counted leaves its stock as-is."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    counted_p = await add_product(client_id, user["id"], name="Counted", quantity=0)
    skipped_p = await add_product(client_id, user["id"], name="Skipped", quantity=0)
    branch = await _make_branch(client, headers, "Main")
    await _allocate(client, headers, branch, counted_p, 30)
    await _allocate(client, headers, branch, skipped_p, 15)

    resp = await client.post(
        "/api/v1/production/stock-counts", json={"branch_id": branch}, headers=headers
    )
    sid = resp.json()["id"]
    await client.post(f"/api/v1/production/stock-counts/{sid}/freeze", headers=headers)

    # Count only one product.
    await client.post(
        f"/api/v1/production/stock-counts/{sid}/count",
        json={"product_id": counted_p, "counted_quantity": 28},
        headers=headers,
    )
    resp = await client.post(
        f"/api/v1/production/stock-counts/{sid}/approve", headers=headers
    )
    assert resp.json()["adjustments_posted"] == 1

    assert await _branch_qty(client, headers, branch, counted_p) == 28
    # The skipped product keeps its original on-hand — never zeroed.
    assert await _branch_qty(client, headers, branch, skipped_p) == 15


@pytest.mark.asyncio
async def test_approve_is_idempotent(client):
    """A second approve is a no-op 409 — adjustments are not double-posted."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=0)
    branch = await _make_branch(client, headers, "Main")
    await _allocate(client, headers, branch, pid, 40)

    resp = await client.post(
        "/api/v1/production/stock-counts", json={"branch_id": branch}, headers=headers
    )
    sid = resp.json()["id"]
    await client.post(f"/api/v1/production/stock-counts/{sid}/freeze", headers=headers)
    await client.post(
        f"/api/v1/production/stock-counts/{sid}/count",
        json={"product_id": pid, "counted_quantity": 35},
        headers=headers,
    )
    first = await client.post(
        f"/api/v1/production/stock-counts/{sid}/approve", headers=headers
    )
    assert first.status_code == 200, first.text
    second = await client.post(
        f"/api/v1/production/stock-counts/{sid}/approve", headers=headers
    )
    assert second.status_code == 409, second.text

    async with db_manager.async_session_maker() as db:
        rows = (
            await db.execute(
                select(Stock_adjustments).where(Stock_adjustments.client_id == client_id)
            )
        ).scalars().all()
    assert len(rows) == 1  # posted exactly once


@pytest.mark.asyncio
async def test_resumable_draft_persists_counts(client):
    """A frozen session's counts survive a re-fetch (the resumable draft)."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=0)
    branch = await _make_branch(client, headers, "Main")
    await _allocate(client, headers, branch, pid, 12)

    resp = await client.post(
        "/api/v1/production/stock-counts", json={"branch_id": branch}, headers=headers
    )
    sid = resp.json()["id"]
    await client.post(f"/api/v1/production/stock-counts/{sid}/freeze", headers=headers)
    await client.post(
        f"/api/v1/production/stock-counts/{sid}/count",
        json={"product_id": pid, "counted_quantity": 9},
        headers=headers,
    )

    # The draft is discoverable in the list, still frozen and re-openable.
    listed = await client.get(
        "/api/v1/production/stock-counts?status=frozen", headers=headers
    )
    assert any(s["id"] == sid for s in listed.json()["items"])

    resumed = await client.get(
        f"/api/v1/production/stock-counts/{sid}", headers=headers
    )
    line = resumed.json()["lines"][0]
    assert line["counted_quantity"] == 9
    assert line["variance"] == -3


@pytest.mark.asyncio
async def test_count_by_barcode(client):
    """A scanned barcode resolves the product within the client scope."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=0)
    await _set_barcode(pid, "5012345678900")
    branch = await _make_branch(client, headers, "Main")
    await _allocate(client, headers, branch, pid, 25)

    resp = await client.post(
        "/api/v1/production/stock-counts", json={"branch_id": branch}, headers=headers
    )
    sid = resp.json()["id"]
    await client.post(f"/api/v1/production/stock-counts/{sid}/freeze", headers=headers)

    resp = await client.post(
        f"/api/v1/production/stock-counts/{sid}/count",
        json={"barcode": "5012345678900", "counted_quantity": 23},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["product_id"] == pid
    assert resp.json()["variance"] == -2


@pytest.mark.asyncio
async def test_client_level_stocktake_updates_product_quantity(client):
    """A no-branch stocktake counts and sets the client-level products.quantity."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=100)

    resp = await client.post(
        "/api/v1/production/stock-counts", json={}, headers=headers
    )
    sid = resp.json()["id"]
    await client.post(f"/api/v1/production/stock-counts/{sid}/freeze", headers=headers)
    resp = await client.post(
        f"/api/v1/production/stock-counts/{sid}/count",
        json={"product_id": pid, "counted_quantity": 90},
        headers=headers,
    )
    assert resp.json()["system_quantity"] == 100
    assert resp.json()["variance"] == -10
    await client.post(f"/api/v1/production/stock-counts/{sid}/approve", headers=headers)

    async with db_manager.async_session_maker() as db:
        qty = (
            await db.execute(select(Products.quantity).where(Products.id == pid))
        ).scalar_one()
    assert int(qty) == 90


@pytest.mark.asyncio
async def test_stocktake_is_owner_scoped(client):
    """A client cannot fetch or drive another client's stocktake (SEC-02)."""
    user_a, token_a, _ = await make_client_account(client)
    user_b, token_b, _ = await make_client_account(client)
    headers_a, headers_b = auth_headers(token_a), auth_headers(token_b)

    resp = await client.post(
        "/api/v1/production/stock-counts", json={}, headers=headers_a
    )
    sid = resp.json()["id"]

    # B cannot see A's session.
    assert (
        await client.get(f"/api/v1/production/stock-counts/{sid}", headers=headers_b)
    ).status_code == 404
    assert (
        await client.post(
            f"/api/v1/production/stock-counts/{sid}/freeze", headers=headers_b
        )
    ).status_code == 404


@pytest.mark.asyncio
async def test_cancel_discards_draft(client):
    """Cancelling a draft/frozen stocktake posts nothing and blocks further action."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    resp = await client.post(
        "/api/v1/production/stock-counts", json={}, headers=headers
    )
    sid = resp.json()["id"]
    resp = await client.post(
        f"/api/v1/production/stock-counts/{sid}/cancel", headers=headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "cancelled"

    # A cancelled session can no longer be frozen.
    assert (
        await client.post(
            f"/api/v1/production/stock-counts/{sid}/freeze", headers=headers
        )
    ).status_code == 409
