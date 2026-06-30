"""#220 (M4·Inventory multi-branch): sale-time enforcement of the branch price.

The branch-pricing slice resolved a branch's effective unit price but did not yet
apply it at checkout — a sale always charged whatever unit price the cart sent.
This wires ``branch_pricing.resolve_price`` into ``POST /pos/transaction`` so a
catalog line rung up at a branch with a price override is charged the branch
price, while a sale with no branch (or a branch with no override) keeps the
chain-wide base price. Mirrors the sale-time branch-tax slice.
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


async def _set_branch_price(client, headers, branch_id, product_id, price):
    resp = await client.put(
        f"/api/v1/pos/branches/{branch_id}/prices",
        json={"product_id": product_id, "price": price},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text


async def _sale(client, headers, pid, *, price, qty=1, branch_id=None):
    payload = {
        "items": [{"product_id": pid, "name": "Item", "price": price, "quantity": qty}],
        "payment_method": "cash",
    }
    if branch_id is not None:
        payload["branch_id"] = branch_id
    return await client.post("/api/v1/pos/transaction", json=payload, headers=headers)


@pytest.mark.asyncio
async def test_sale_at_branch_uses_branch_price_override(client):
    """A product with base 100 but a branch override of 80 is charged 80 at that
    branch even when the cart still sends the chain base price (server enforces)."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    branch = await _make_branch(client, headers, "Airport")
    pid = await add_product(client_id, user["id"], name="Item", quantity=10, price=100.0)
    await _set_branch_price(client, headers, branch, pid, 80.0)

    resp = await _sale(client, headers, pid, price=100.0, qty=1, branch_id=branch)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["subtotal"] == 80.0
    # statutory chain VAT 15 % on the branch-enforced 80.00
    assert body["vat_amount"] == 12.0
    assert body["total_amount"] == 92.0


@pytest.mark.asyncio
async def test_sale_at_branch_without_override_uses_base_price(client):
    """A branch with no price override charges the chain-wide base price."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    branch = await _make_branch(client, headers, "Downtown")
    pid = await add_product(client_id, user["id"], name="Item", quantity=10, price=100.0)

    resp = await _sale(client, headers, pid, price=100.0, qty=1, branch_id=branch)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["subtotal"] == 100.0
    assert body["total_amount"] == 115.0


@pytest.mark.asyncio
async def test_sale_without_branch_ignores_branch_override(client):
    """A non-branch sale uses the submitted/base price — a branch override on the
    product must not leak into a sale that carries no branch_id."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    branch = await _make_branch(client, headers, "Mall")
    pid = await add_product(client_id, user["id"], name="Item", quantity=10, price=100.0)
    await _set_branch_price(client, headers, branch, pid, 80.0)

    resp = await _sale(client, headers, pid, price=100.0, qty=1)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["subtotal"] == 100.0
    assert body["total_amount"] == 115.0
