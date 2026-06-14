"""ISSUE-064 — catalog CSV import/export.

A merchant can export their product catalog as a CSV and bulk create/update
products by uploading a CSV. Invalid rows are reported (not silently dropped),
and an export round-trips cleanly back through import.
"""
import csv
import io

import pytest

from conftest import add_product, auth_headers, make_client_account


def _parse_csv(text: str):
    return list(csv.DictReader(io.StringIO(text)))


async def _import_csv(client, headers, csv_text: str):
    return await client.post(
        "/api/v1/entities/products/import",
        files={"file": ("catalog.csv", csv_text.encode("utf-8"), "text/csv")},
        headers=headers,
    )


async def _list_products(client, headers):
    resp = await client.get("/api/v1/entities/products", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["items"]


@pytest.mark.asyncio
async def test_export_returns_owner_catalog_as_csv(client):
    """AC1: export produces a CSV of (only) the merchant's own catalog."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await add_product(client_id, user["id"], name="Cola", price=5.0, quantity=10)
    await add_product(client_id, user["id"], name="Water", price=2.5, quantity=20)

    # A different merchant's product must not leak into this export.
    other_user, _, other_cid = await make_client_account(client)
    await add_product(other_cid, other_user["id"], name="Secret", price=99.0)

    resp = await client.get("/api/v1/entities/products/export", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/csv")

    rows = _parse_csv(resp.text)
    names = {r["name"] for r in rows}
    assert names == {"Cola", "Water"}
    cola = next(r for r in rows if r["name"] == "Cola")
    assert float(cola["price"]) == 5.0
    assert float(cola["quantity"]) == 10


@pytest.mark.asyncio
async def test_import_creates_products(client):
    """AC2: import creates products from a CSV."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    csv_text = (
        "name,barcode,category,price,quantity,vat_rate\n"
        "Espresso,1001,Drinks,8.0,50,15\n"
        "Latte,1002,Drinks,12.5,30,15\n"
    )
    resp = await _import_csv(client, headers, csv_text)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["created"] == 2
    assert body["updated"] == 0
    assert body["errors"] == []

    items = await _list_products(client, headers)
    by_name = {p["name"]: p for p in items}
    assert set(by_name) == {"Espresso", "Latte"}
    assert by_name["Espresso"]["price"] == 8.0
    assert by_name["Espresso"]["barcode"] == "1001"
    assert by_name["Latte"]["quantity"] == 30


@pytest.mark.asyncio
async def test_import_updates_existing_by_barcode(client):
    """AC2: a barcode matching an existing product updates it, not duplicates it."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    # Seed one product, then import a CSV carrying the same barcode at a new price.
    first = await _import_csv(
        client, headers, "name,barcode,price,quantity\nMilk,7000,4.0,10\n"
    )
    assert first.json()["created"] == 1

    resp = await _import_csv(
        client, headers, "name,barcode,price,quantity\nMilk 1L,7000,4.5,25\n"
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["created"] == 0
    assert body["updated"] == 1

    items = await _list_products(client, headers)
    milk = [p for p in items if p["barcode"] == "7000"]
    assert len(milk) == 1  # updated in place, not duplicated
    assert milk[0]["name"] == "Milk 1L"
    assert milk[0]["price"] == 4.5
    assert milk[0]["quantity"] == 25


@pytest.mark.asyncio
async def test_import_reports_invalid_rows_without_dropping_valid(client):
    """AC2: invalid rows are reported (not silently dropped); valid rows still import."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    csv_text = (
        "name,barcode,price,quantity\n"
        "Good,1,5.0,10\n"          # valid
        ",2,3.0,1\n"               # missing name
        "BadPrice,3,abc,2\n"       # non-numeric price
        "NoPrice,4,,7\n"           # missing price
    )
    resp = await _import_csv(client, headers, csv_text)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["created"] == 1
    assert body["total_rows"] == 4
    bad_rows = {e["row"] for e in body["errors"]}
    assert bad_rows == {2, 3, 4}

    items = await _list_products(client, headers)
    assert {p["name"] for p in items} == {"Good"}


@pytest.mark.asyncio
async def test_export_then_import_round_trips(client):
    """AC3: an exported catalog re-imports cleanly (idempotent upsert by barcode)."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await add_product(
        client_id, user["id"], name="Tea", price=6.0, quantity=15,
    )
    await add_product(
        client_id, user["id"], name="Juice", price=9.0, quantity=8,
    )
    # Give them barcodes so the round-trip upserts in place rather than duplicating.
    items = await _list_products(client, headers)
    for i, p in enumerate(items, start=1):
        r = await client.put(
            f"/api/v1/entities/products/{p['id']}",
            json={"barcode": f"BC-{i}"},
            headers=headers,
        )
        assert r.status_code == 200, r.text

    # Export, then re-import the exact bytes.
    export = await client.get("/api/v1/entities/products/export", headers=headers)
    assert export.status_code == 200, export.text
    resp = await _import_csv(client, headers, export.text)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["errors"] == []
    assert body["updated"] == 2
    assert body["created"] == 0

    # Catalog is unchanged (no duplicates, same prices) after the round-trip.
    after = await _list_products(client, headers)
    assert len(after) == 2
    by_name = {p["name"]: p for p in after}
    assert by_name["Tea"]["price"] == 6.0
    assert by_name["Juice"]["quantity"] == 8
