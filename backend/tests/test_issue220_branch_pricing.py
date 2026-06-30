"""#220 (M4·Inventory multi-branch): branch-level pricing.

A product carries a chain-wide default price (``products.price``); a branch may
override it for itself. Resolving an effective price returns the branch override
when one exists, else falls back to the base price. Overrides are owner-scoped
(SEC-02) and one-per-(branch, product) — upserted, never duplicated.
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


async def _set_price(client, headers, branch_id, product_id, price):
    resp = await client.put(
        f"/api/v1/pos/branches/{branch_id}/prices",
        json={"product_id": product_id, "price": price},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _resolve(client, headers, branch_id, product_id):
    resp = await client.get(
        f"/api/v1/pos/branches/{branch_id}/prices/resolve?product_id={product_id}",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_resolve_returns_branch_override(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], price=10.0)
    branch = await _make_branch(client, headers, "Airport")

    await _set_price(client, headers, branch, pid, 14.5)

    resolved = await _resolve(client, headers, branch, pid)
    assert resolved["price"] == 14.5
    assert resolved["is_override"] is True


@pytest.mark.asyncio
async def test_resolve_falls_back_to_base_price(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], price=10.0)
    branch_a = await _make_branch(client, headers, "Airport")
    branch_b = await _make_branch(client, headers, "Suburb")

    # Override only branch A; branch B resolves to the chain-wide base price.
    await _set_price(client, headers, branch_a, pid, 14.5)

    resolved = await _resolve(client, headers, branch_b, pid)
    assert resolved["price"] == 10.0
    assert resolved["is_override"] is False


@pytest.mark.asyncio
async def test_set_price_is_idempotent_upsert(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], price=10.0)
    branch = await _make_branch(client, headers, "Airport")

    await _set_price(client, headers, branch, pid, 14.5)
    await _set_price(client, headers, branch, pid, 16.0)  # update, not insert

    listing = await client.get(
        f"/api/v1/pos/branches/{branch}/prices", headers=headers
    )
    assert listing.status_code == 200, listing.text
    items = listing.json()["items"]
    rows = [i for i in items if i["product_id"] == pid]
    assert len(rows) == 1
    assert rows[0]["price"] == 16.0


@pytest.mark.asyncio
async def test_override_is_owner_scoped(client):
    """A second tenant's branch override never leaks into the first tenant's
    resolution (SEC-02): each tenant sees only their own branch prices."""
    user_a, token_a, cid_a = await make_client_account(client)
    headers_a = auth_headers(token_a)
    pid_a = await add_product(cid_a, user_a["id"], price=10.0)
    branch_a = await _make_branch(client, headers_a, "A-Airport")
    await _set_price(client, headers_a, branch_a, pid_a, 14.5)

    user_b, token_b, cid_b = await make_client_account(client)
    headers_b = auth_headers(token_b)

    # Tenant B cannot see tenant A's override listing.
    listing_b = await client.get(
        f"/api/v1/pos/branches/{branch_a}/prices", headers=headers_b
    )
    assert listing_b.status_code == 200, listing_b.text
    assert listing_b.json()["items"] == []
