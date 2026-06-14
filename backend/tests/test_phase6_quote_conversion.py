"""ISSUE-056 — quote→sale conversion + quotation status lifecycle.

A quotation (عرض سعر) is a non-fiscal pre-sale document. These tests cover turning
an accepted quote into a real sale through the **same** canonical atomic sale core
(``services.sale_core.execute_sale``) the POS uses — so the resulting invoice is
ZATCA-stamped where applicable — and the status lifecycle
(draft → sent → accepted → converted, plus expired) that gates it.
"""
import json

from sqlalchemy import func, select

from conftest import add_product, auth_headers, make_client_account
from core.database import db_manager
from models.transactions import Transactions


async def _create_quote(client, headers, product_id, **overrides):
    payload = {
        "customer_name": "Acme Co",
        "items_json": json.dumps(
            [{"product_id": product_id, "name": "Widget", "quantity": 2, "price": 50.0}]
        ),
        "subtotal": 100.0,
        "discount_amount": 0.0,
        "vat_amount": 15.0,
        "total_amount": 115.0,
    }
    payload.update(overrides)
    resp = await client.post(
        "/api/v1/entities/quotations", json=payload, headers=headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_convert_quote_mints_zatca_sale_and_links_it(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Widget", quantity=10, price=50.0)
    quote = await _create_quote(client, headers, pid)

    resp = await client.post(
        f"/api/v1/entities/quotations/{quote['id']}/convert",
        json={"payment_method": "cash"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # A real sale was minted through the canonical path: it has an INV- number and
    # a stamped fiscal document (ZATCA enabled by default).
    assert body["transaction_id"]
    assert body["invoice_number"].startswith("INV-")
    assert body["zatca_document_id"] is not None
    assert body["zatca_status"] == "signed"

    # The quotation is now `converted` and links the resulting sale (AC3).
    assert body["status"] == "converted"
    assert body["transaction_id"]

    quote_after = (
        await client.get(
            f"/api/v1/entities/quotations/{quote['id']}", headers=headers
        )
    ).json()
    assert quote_after["status"] == "converted"
    assert quote_after["converted_transaction_id"] == body["transaction_id"]

    # The sale really exists and carries the quote's totals.
    async with db_manager.async_session_maker() as db:
        txn = (
            await db.execute(
                select(Transactions).where(
                    Transactions.id == body["transaction_id"]
                )
            )
        ).scalar_one()
        assert abs(txn.total_amount - 115.0) < 0.01
        assert txn.status == "completed"


async def test_status_lifecycle_transitions_are_enforced(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Widget", quantity=10, price=50.0)
    quote = await _create_quote(client, headers, pid)
    assert quote["status"] == "draft"

    async def _set_status(target):
        return await client.put(
            f"/api/v1/entities/quotations/{quote['id']}/status",
            json={"status": target},
            headers=headers,
        )

    # A legal forward transition succeeds and is visible.
    resp = await _set_status("sent")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "sent"

    resp = await _set_status("accepted")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "accepted"

    # An illegal backward transition is rejected.
    resp = await _set_status("draft")
    assert resp.status_code == 400, resp.text

    # `converted` can't be set directly — it's reached only via /convert.
    resp = await _set_status("converted")
    assert resp.status_code == 400, resp.text


async def test_converted_quote_cannot_be_converted_again(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Widget", quantity=10, price=50.0)
    quote = await _create_quote(client, headers, pid)

    first = await client.post(
        f"/api/v1/entities/quotations/{quote['id']}/convert",
        json={},
        headers=headers,
    )
    assert first.status_code == 200, first.text

    # A second conversion is rejected — the quote is terminal (`converted`), so no
    # duplicate sale is minted.
    second = await client.post(
        f"/api/v1/entities/quotations/{quote['id']}/convert",
        json={},
        headers=headers,
    )
    assert second.status_code == 400, second.text

    # Exactly one sale exists for this client.
    async with db_manager.async_session_maker() as db:
        count = (
            await db.execute(
                select(func.count(Transactions.id)).where(
                    Transactions.client_id == client_id,
                    Transactions.status == "completed",
                )
            )
        ).scalar()
        assert count == 1
