"""#220 (M4·Inventory multi-branch): sale-time enforcement of the branch VAT rate.

The branch-tax slice resolved a branch's effective VAT rate but did not yet apply
it at checkout — a sale always used the chain-wide rate. This wires
``branch_tax.resolve_tax_rate`` into ``POST /pos/transaction`` so a sale rung up at
a branch with its own VAT override is taxed at that branch's rate, while a sale
with no branch (or a branch with no override) still falls back to the chain rate.
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


async def _set_tax(client, headers, branch_id, vat_rate):
    resp = await client.put(
        f"/api/v1/pos/branches/{branch_id}/tax-rate",
        json={"vat_rate": vat_rate},
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
async def test_sale_at_branch_uses_branch_vat_rate(client):
    """A 100.00 line at a branch overriding VAT to 5 % is taxed 5.00, total 105.00."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    branch = await _make_branch(client, headers, "Airport")
    await _set_tax(client, headers, branch, 5.0)
    pid = await add_product(client_id, user["id"], name="Item", quantity=10, price=100.0)

    resp = await _sale(client, headers, pid, price=100.0, qty=1, branch_id=branch)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["subtotal"] == 100.0
    assert body["vat_amount"] == 5.0
    assert body["total_amount"] == 105.0


@pytest.mark.asyncio
async def test_sale_at_branch_without_override_uses_chain_rate(client):
    """A branch with no VAT override falls back to the statutory chain 15 %."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    branch = await _make_branch(client, headers, "Downtown")
    pid = await add_product(client_id, user["id"], name="Item", quantity=10, price=100.0)

    resp = await _sale(client, headers, pid, price=100.0, qty=1, branch_id=branch)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["vat_amount"] == 15.0
    assert body["total_amount"] == 115.0


@pytest.mark.asyncio
async def test_sale_without_branch_uses_chain_rate(client):
    """A non-branch sale is unaffected — still the chain 15 %."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Item", quantity=10, price=100.0)

    resp = await _sale(client, headers, pid, price=100.0, qty=1)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["vat_amount"] == 15.0
    assert body["total_amount"] == 115.0
