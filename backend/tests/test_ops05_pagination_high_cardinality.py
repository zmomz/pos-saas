"""F-OPS-1 / OPS-05 — server-side pagination on the high-cardinality list endpoints.

Before the fix these three endpoints loaded *every* matching row into memory and
returned it in one response (no LIMIT): the ZATCA document archive (one row per
invoice, 6-year retention), issued gift cards, and parked (held) tickets. These
tests pin that each now (a) accepts ``skip``/``limit``, (b) bounds the page to
``limit`` rows, (c) reports the full ``total`` so the UI can page, and (d) walks
cleanly with ``skip`` without overlap.
"""
from sqlalchemy import select

from conftest import add_product, auth_headers, make_client_account
from core.database import db_manager
from models.clients import Clients


def _items(pid, *, price=10.0, qty=1):
    return [{"product_id": pid, "name": "Cola", "price": price, "quantity": qty}]


async def _set_vat(client_id: int, vat: str = "300000000000003"):
    async with db_manager.async_session_maker() as db:
        row = (
            await db.execute(select(Clients).where(Clients.id == client_id))
        ).scalar_one()
        row.vat_number = vat
        await db.commit()


# ---------------------------------------------------------------------------
# Gift cards — GET /api/v1/gift-cards
# ---------------------------------------------------------------------------
async def test_gift_cards_list_is_paginated(client):
    _user, token, _client_id = await make_client_account(client)
    headers = auth_headers(token)
    for _ in range(3):
        resp = await client.post(
            "/api/v1/gift-cards", json={"amount": 50.0}, headers=headers
        )
        assert resp.status_code == 201, resp.text

    first = (
        await client.get("/api/v1/gift-cards?skip=0&limit=2", headers=headers)
    ).json()
    assert first["total"] == 3, "total is the full count, not the page size"
    assert len(first["items"]) == 2, "limit bounds the page"

    second = (
        await client.get("/api/v1/gift-cards?skip=2&limit=2", headers=headers)
    ).json()
    assert second["total"] == 3
    assert len(second["items"]) == 1, "the remainder after skipping a full page"

    # Pages do not overlap — skip actually advances the window.
    ids = {c["id"] for c in first["items"]} | {c["id"] for c in second["items"]}
    assert len(ids) == 3


# ---------------------------------------------------------------------------
# Held tickets — GET /api/v1/pos/held
# ---------------------------------------------------------------------------
async def test_held_list_is_paginated(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=99, price=10.0)
    for n in range(3):
        resp = await client.post(
            "/api/v1/pos/hold",
            json={"items": _items(pid), "label": f"Table {n}"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text

    page = (await client.get("/api/v1/pos/held?skip=0&limit=2", headers=headers)).json()
    assert page["total"] == 3
    assert len(page["items"]) == 2

    rest = (await client.get("/api/v1/pos/held?skip=2&limit=2", headers=headers)).json()
    assert rest["total"] == 3
    assert len(rest["items"]) == 1
    ids = {t["id"] for t in page["items"]} | {t["id"] for t in rest["items"]}
    assert len(ids) == 3


# ---------------------------------------------------------------------------
# ZATCA documents — GET /api/v1/zatca/documents
# ---------------------------------------------------------------------------
async def test_zatca_documents_list_is_paginated(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _set_vat(client_id)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=99, price=10.0)

    # Two sales auto-sign -> two retained fiscal documents.
    for _ in range(2):
        resp = await client.post(
            "/api/v1/pos/transaction",
            json={"items": _items(pid, qty=2), "payment_method": "cash"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text

    full = (await client.get("/api/v1/zatca/documents", headers=headers)).json()
    assert full["total"] == 2
    assert len(full["items"]) == 2

    first = (
        await client.get("/api/v1/zatca/documents?skip=0&limit=1", headers=headers)
    ).json()
    assert first["total"] == 2, "total reflects the whole archive, not the page"
    assert len(first["items"]) == 1, "limit bounds the materialized rows"

    second = (
        await client.get("/api/v1/zatca/documents?skip=1&limit=1", headers=headers)
    ).json()
    assert len(second["items"]) == 1
    assert first["items"][0]["id"] != second["items"][0]["id"]
