"""ISSUE-224 (M4 Inventory) — vendor returns / supplier credit notes.

Procurement governance, second slice: when a merchant returns received goods to a
vendor, stock is drawn back down and the value owed is recorded as a **supplier
credit note** on an append-only ledger. These tests pin the slice:

- a vendor return decrements product stock and posts a supplier credit note for the
  returned value (default per-unit = the product's cost price, overridable per line);
- the supplier's outstanding credit balance is the running sum of its credit notes;
- you cannot return more than is on hand, nor a non-positive quantity;
- returns are owner-scoped (another tenant's supplier/product is invisible → 404).
"""
import pytest

from conftest import (
    add_product,
    auth_headers,
    get_product_quantity,
    make_client_account,
)


async def _create_supplier(client, headers, name="Acme Supply"):
    resp = await client.post(
        "/api/v1/entities/suppliers",
        json={"name": name},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _return(client, headers, supplier_id, lines, **extra):
    return await client.post(
        f"/api/v1/entities/suppliers/{supplier_id}/returns",
        json={"lines": lines, **extra},
        headers=headers,
    )


@pytest.mark.asyncio
async def test_vendor_return_decrements_stock_and_posts_credit_note(client):
    """Returning goods draws stock down and raises a supplier credit note for the value."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=10, cost_price=4.0)
    sid = await _create_supplier(client, headers)

    r = await _return(client, headers, sid, [{"product_id": pid, "quantity": 3}])
    assert r.status_code == 200, r.text
    body = r.json()
    # 3 units returned at the product's 4.00 cost → a 12.00 credit note.
    assert body["amount"] == pytest.approx(12.0)
    assert body["balance"] == pytest.approx(12.0)
    assert body["returned_items"] == 1

    # Stock fell by the returned quantity.
    assert await get_product_quantity(pid) == 7

    # The credit note is observable on the supplier's credit endpoint.
    bal = await client.get(
        f"/api/v1/entities/suppliers/{sid}/credit", headers=headers
    )
    assert bal.status_code == 200, bal.text
    assert bal.json()["balance"] == pytest.approx(12.0)
    assert len(bal.json()["history"]) == 1


@pytest.mark.asyncio
async def test_credit_notes_accumulate_into_running_balance(client):
    """Successive vendor returns sum into the supplier's outstanding credit balance."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=10, cost_price=5.0)
    sid = await _create_supplier(client, headers)

    r1 = await _return(client, headers, sid, [{"product_id": pid, "quantity": 2}])
    assert r1.status_code == 200, r1.text
    assert r1.json()["balance"] == pytest.approx(10.0)

    # A per-line cost override prices the second note independently of cost_price.
    r2 = await _return(client, headers, sid, [{"product_id": pid, "quantity": 1, "cost": 7.0}])
    assert r2.status_code == 200, r2.text
    assert r2.json()["amount"] == pytest.approx(7.0)
    assert r2.json()["balance"] == pytest.approx(17.0)

    bal = await client.get(f"/api/v1/entities/suppliers/{sid}/credit", headers=headers)
    assert bal.json()["balance"] == pytest.approx(17.0)
    assert len(bal.json()["history"]) == 2
    assert await get_product_quantity(pid) == 7


@pytest.mark.asyncio
async def test_cannot_return_more_than_on_hand(client):
    """Returning more than current stock is rejected and books nothing."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=2, cost_price=4.0)
    sid = await _create_supplier(client, headers)

    r = await _return(client, headers, sid, [{"product_id": pid, "quantity": 5}])
    assert r.status_code == 400, r.text
    # Stock untouched and no credit note posted.
    assert await get_product_quantity(pid) == 2
    bal = await client.get(f"/api/v1/entities/suppliers/{sid}/credit", headers=headers)
    assert bal.json()["balance"] == pytest.approx(0.0)
    assert bal.json()["history"] == []


@pytest.mark.asyncio
async def test_non_positive_quantity_is_rejected(client):
    """A zero/negative return quantity is rejected (400)."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=5, cost_price=4.0)
    sid = await _create_supplier(client, headers)

    r = await _return(client, headers, sid, [{"product_id": pid, "quantity": 0}])
    assert r.status_code == 400, r.text
    assert await get_product_quantity(pid) == 5


@pytest.mark.asyncio
async def test_vendor_return_is_owner_scoped(client):
    """Another tenant's supplier is invisible — a return against it 404s."""
    user_a, token_a, client_a = await make_client_account(client)
    headers_a = auth_headers(token_a)
    sid_a = await _create_supplier(client, headers_a)

    user_b, token_b, client_b = await make_client_account(client)
    headers_b = auth_headers(token_b)
    pid_b = await add_product(client_b, user_b["id"], quantity=5, cost_price=4.0)

    # Tenant B cannot post a return against tenant A's supplier.
    r = await _return(client, headers_b, sid_a, [{"product_id": pid_b, "quantity": 1}])
    assert r.status_code == 404, r.text

    # And cannot read tenant A's supplier credit.
    bal = await client.get(
        f"/api/v1/entities/suppliers/{sid_a}/credit", headers=headers_b
    )
    assert bal.status_code == 404, bal.text


@pytest.mark.asyncio
async def test_branch_return_draws_from_branch_ledger(client):
    """A branch-scoped return draws stock out of the per-branch ledger (INV-07)."""
    from conftest import db_manager
    from services.branch_stock import _get_row, set_branch_stock

    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=99, cost_price=3.0)
    sid = await _create_supplier(client, headers)

    branch_id = 1
    async with db_manager.async_session_maker() as db:
        await set_branch_stock(db, user["id"], client_id, branch_id, pid, 8)

    r = await _return(
        client, headers, sid, [{"product_id": pid, "quantity": 3}], branch_id=branch_id
    )
    assert r.status_code == 200, r.text
    assert r.json()["balance"] == pytest.approx(9.0)

    # The branch ledger fell by 3; the client-level aggregate is untouched.
    async with db_manager.async_session_maker() as db:
        row = await _get_row(db, client_id, branch_id, pid)
        assert row.quantity == 5
    assert await get_product_quantity(pid) == 99
