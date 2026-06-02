"""POS sale + inventory deduction atomicity tests."""
from conftest import (
    add_product,
    auth_headers,
    get_product_quantity,
    make_client_account,
)


async def _txn_count(client, headers) -> int:
    resp = await client.get("/api/v1/pos/transactions", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["total"]


async def test_sale_deducts_stock_atomically(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=5, price=10.0)

    resp = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Cola", "price": 10.0, "quantity": 3}],
            "payment_method": "cash",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert await get_product_quantity(pid) == 2


async def test_oversell_rolls_back_entire_sale(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Juice", quantity=2, price=5.0)

    before = await _txn_count(client, headers)

    resp = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Juice", "price": 5.0, "quantity": 10}],
            "payment_method": "cash",
        },
        headers=headers,
    )
    assert resp.status_code == 400, resp.text

    # Atomic: stock unchanged AND no transaction persisted AND counter not consumed.
    assert await get_product_quantity(pid) == 2
    assert await _txn_count(client, headers) == before


async def test_allow_negative_stock_override(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Loose", quantity=1, price=2.0)

    resp = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Loose", "price": 2.0, "quantity": 5}],
            "payment_method": "cash",
            "allow_negative_stock": True,
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert await get_product_quantity(pid) <= 0
