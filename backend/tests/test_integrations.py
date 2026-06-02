"""Tests for the wired-up integration endpoints (bulk import, global search)."""
from conftest import auth_headers, make_client_account


async def test_bulk_import_products(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    csv_content = (
        "name,price,quantity,category\n"
        "Apple,1.50,100,Fruit\n"
        "Banana,0.75,50,Fruit\n"
        ",2.00,5,Bad\n"  # missing name -> error row
    )
    resp = await client.post(
        "/api/v1/integrations/bulk-import/products",
        json={"csv_content": csv_content},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["imported"] == 2
    assert body["error_count"] == 1

    # Imported products are now searchable.
    search = await client.get(
        "/api/v1/integrations/search", params={"q": "Apple"}, headers=headers
    )
    assert search.status_code == 200, search.text
    names = [p["name"] for p in search.json()["products"]]
    assert "Apple" in names


async def test_global_search_scoped_to_user(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await client.post(
        "/api/v1/integrations/bulk-import/products",
        json={"csv_content": "name,price\nZebraSnack,9.0\n"},
        headers=headers,
    )

    other_user, other_token, _ = await make_client_account(client)
    other = await client.get(
        "/api/v1/integrations/search", params={"q": "ZebraSnack"}, headers=auth_headers(other_token)
    )
    assert other.status_code == 200
    # The other user must not see the first user's product.
    assert other.json()["products"] == []
