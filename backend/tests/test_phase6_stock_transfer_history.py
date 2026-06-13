"""ISSUE-060 — inter-branch stock-transfer history (INV, P2 inventory).

Transfers execute (F-032) and write a ``stock_transfers`` audit row, but there was
no way to read that history back. These tests pin the corrected behavior of a
``GET /api/v1/production/branches/transfers`` endpoint:

- it returns the caller's past transfers, newest first, with the fields a history
  view needs (from/to branch, product, qty, status, timestamp);
- it is owner-scoped — a client never sees another client's transfers (SEC-02);
- it can be filtered by branch (either leg) and by product.
"""
import pytest

from conftest import add_product, auth_headers, make_client_account


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


async def _transfer(client, headers, src, dst, pid, qty):
    resp = await client.post(
        "/api/v1/production/branches/transfer",
        json={"from_branch_id": src, "to_branch_id": dst, "product_id": pid, "quantity": qty},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_history_lists_transfers_newest_first(client):
    """Past transfers come back newest-first with the fields a history view needs."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=0, price=10.0)
    src = await _make_branch(client, headers, "Main")
    dst = await _make_branch(client, headers, "Second")
    await _allocate(client, headers, src, pid, 50)

    await _transfer(client, headers, src, dst, pid, 5)
    await _transfer(client, headers, src, dst, pid, 7)

    resp = await client.get("/api/v1/production/branches/transfers", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 2
    items = body["items"]
    assert len(items) == 2
    # Newest first (the qty=7 move was last).
    assert items[0]["quantity"] == 7
    assert items[1]["quantity"] == 5
    row = items[0]
    assert row["from_branch_id"] == src
    assert row["to_branch_id"] == dst
    assert row["product_id"] == pid
    assert row["product_name"]
    assert row["status"] == "received"
    assert row["created_at"]


@pytest.mark.asyncio
async def test_history_is_owner_scoped(client):
    """A client never sees another client's transfers (SEC-02)."""
    user_a, token_a, client_id_a = await make_client_account(client)
    headers_a = auth_headers(token_a)
    pid_a = await add_product(client_id_a, user_a["id"], quantity=0, price=10.0)
    src_a = await _make_branch(client, headers_a, "A-Main")
    dst_a = await _make_branch(client, headers_a, "A-Second")
    await _allocate(client, headers_a, src_a, pid_a, 30)
    await _transfer(client, headers_a, src_a, dst_a, pid_a, 4)

    # A second, unrelated client reads its (empty) history.
    _user_b, token_b, _ = await make_client_account(client)
    headers_b = auth_headers(token_b)
    resp = await client.get("/api/v1/production/branches/transfers", headers=headers_b)
    assert resp.status_code == 200, resp.text
    assert resp.json()["items"] == []


@pytest.mark.asyncio
async def test_history_filters_by_branch_and_product(client):
    """The history can be filtered by branch (either leg) and by product."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    p1 = await add_product(client_id, user["id"], quantity=0, price=10.0)
    p2 = await add_product(client_id, user["id"], quantity=0, price=10.0)
    a = await _make_branch(client, headers, "A")
    b = await _make_branch(client, headers, "B")
    c = await _make_branch(client, headers, "C")
    await _allocate(client, headers, a, p1, 50)
    await _allocate(client, headers, a, p2, 50)

    await _transfer(client, headers, a, b, p1, 5)  # A→B, p1
    await _transfer(client, headers, a, c, p2, 6)  # A→C, p2

    # branch_id matches either leg: filtering on B returns only the A→B move.
    resp = await client.get(
        "/api/v1/production/branches/transfers", params={"branch_id": b}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["to_branch_id"] == b and items[0]["product_id"] == p1

    # product_id filter returns only that product's moves.
    resp = await client.get(
        "/api/v1/production/branches/transfers", params={"product_id": p2}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["product_id"] == p2
