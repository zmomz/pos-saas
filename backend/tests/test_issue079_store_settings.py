"""ISSUE-079 — Merchant store-settings screen.

A merchant needs one screen to edit the store-level identity and operational
defaults that feed every receipt/invoice: the VAT/CR registration numbers, the
receipt footer line, the branch profile (address/city/phone) and the business
hours. These live server-side (so they follow the merchant across devices and
drive the fiscal documents) and are exercised here through the public HTTP
interface (``/api/v1/store-settings``).

The fiscally-authoritative fields already modelled on the ``clients`` row —
``business_name`` (the seller name) and ``vat_number`` — are written through from
this screen so the existing receipt/invoice/ZATCA paths (which read
``clients.*``) reflect the merchant's edits with no change to those code paths.
The remaining merchant-level fields (CR number, receipt footer, branch profile,
business hours) live on a dedicated ``store_settings`` row keyed by the tenancy
owner.
"""
import base64
import json

import pytest

from conftest import auth_headers, make_client_account, add_product

pytestmark = pytest.mark.asyncio

STORE_SETTINGS_URL = "/api/v1/store-settings"


async def test_store_settings_persist_and_reload(client):
    """A merchant can save VAT/CR, receipt footer, branch profile and hours, and a
    later load returns exactly what was saved (AC1)."""
    _user, token, _client_id = await make_client_account(client)

    hours = [
        {"day": "sun", "open": "09:00", "close": "23:00", "closed": False},
        {"day": "fri", "open": "", "close": "", "closed": True},
    ]
    payload = {
        "store_name": "Falafel House",
        "vat_number": "300000000000003",
        "cr_number": "1010101010",
        "receipt_footer": "نشكر زيارتكم — يرجى الاحتفاظ بالفاتورة",
        "address": "King Fahd Rd",
        "city": "Riyadh",
        "phone": "+966500000000",
        "business_hours": hours,
    }
    put = await client.put(STORE_SETTINGS_URL, headers=auth_headers(token), json=payload)
    assert put.status_code == 200, put.text

    got = await client.get(STORE_SETTINGS_URL, headers=auth_headers(token))
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["store_name"] == "Falafel House"
    assert body["vat_number"] == "300000000000003"
    assert body["cr_number"] == "1010101010"
    assert body["receipt_footer"] == "نشكر زيارتكم — يرجى الاحتفاظ بالفاتورة"
    assert body["address"] == "King Fahd Rd"
    assert body["city"] == "Riyadh"
    assert body["phone"] == "+966500000000"
    assert body["business_hours"] == hours


async def test_store_settings_are_scoped_to_the_merchant(client):
    """One merchant's store settings never leak into another merchant's (AC1)."""
    _a, token_a, _ = await make_client_account(client)
    _b, token_b, _ = await make_client_account(client)

    saved = await client.put(
        STORE_SETTINGS_URL,
        headers=auth_headers(token_a),
        json={"store_name": "Merchant A", "cr_number": "1111111111", "receipt_footer": "A footer"},
    )
    assert saved.status_code == 200, saved.text

    other = await client.get(STORE_SETTINGS_URL, headers=auth_headers(token_b))
    assert other.status_code == 200, other.text
    body = other.json()
    # B never saved: its own client name shows, but A's CR/footer must not leak.
    assert body["store_name"] == "Test Shop"
    assert body["cr_number"] is None
    assert body["receipt_footer"] is None


async def _make_sale(client, token, user_id, client_id):
    pid = await add_product(client_id, user_id, quantity=10, price=10.0)
    sale = await client.post(
        "/api/v1/pos/transaction",
        headers=auth_headers(token),
        json={
            "items": [{"product_id": pid, "name": "Widget", "price": 10.0, "quantity": 1}],
            "payment_method": "cash",
        },
    )
    assert sale.status_code in (200, 201), sale.text
    return sale.json()["id"]


async def test_receipt_footer_flows_into_the_printed_receipt(client):
    """A receipt footer saved on the store-settings screen reaches the ESC/POS
    receipt renderer, changing the printed output (AC2 — values flow into
    receipts)."""
    user, token, client_id = await make_client_account(client)
    txn_id = await _make_sale(client, token, user["id"], client_id)

    before = await client.get(
        f"/api/v1/pos/transactions/{txn_id}/escpos", headers=auth_headers(token)
    )
    assert before.status_code == 200, before.text
    bytes_before = base64.b64decode(before.json()["data"])

    saved = await client.put(
        STORE_SETTINGS_URL,
        headers=auth_headers(token),
        json={"receipt_footer": "زورونا مرة أخرى — متجر الاختبار"},
    )
    assert saved.status_code == 200, saved.text

    after = await client.get(
        f"/api/v1/pos/transactions/{txn_id}/escpos", headers=auth_headers(token)
    )
    assert after.status_code == 200, after.text
    bytes_after = base64.b64decode(after.json()["data"])

    assert bytes_after != bytes_before, (
        "the store-settings receipt footer must reach the receipt renderer"
    )


async def test_vat_written_through_to_the_authoritative_client_row(client):
    """Saving the VAT number on the store-settings screen writes it through to the
    fiscally-authoritative ``clients`` row that the invoice/ZATCA paths read
    (AC2)."""
    from core.database import db_manager
    from sqlalchemy import select
    from models.clients import Clients

    user, token, client_id = await make_client_account(client)

    saved = await client.put(
        STORE_SETTINGS_URL,
        headers=auth_headers(token),
        json={"vat_number": "311111111111113"},
    )
    assert saved.status_code == 200, saved.text

    async with db_manager.async_session_maker() as session:
        vat = (
            await session.execute(select(Clients.vat_number).where(Clients.id == client_id))
        ).scalar_one()
    assert vat == "311111111111113", "VAT must persist onto the authoritative client row"
