"""ISSUE-071 — In-app thermal print of the proforma check + final receipt.

The restaurant flow already renders an always-Arabic proforma (*فاتورة مبدئية*)
and a fiscal settle receipt as base64 ESC/POS streams (#45). This slice routes
both to the merchant's saved/selected **receipt** printer (#47): the response
echoes the resolved device so the browser streams to it instead of re-prompting,
and the printer's ``paper_size`` overrides the template's so the raster matches
the actual head — exactly how the POS ``/escpos`` receipt and the KDS KOT already
route. Both printables stay always-Arabic and honor the template.

Behaviors:
- Printing a proforma check carries the resolved receipt printer + honors its
  paper_size override, while staying a non-fiscal Arabic check (no QR).
- Settling a ticket carries the resolved receipt printer + honors its paper_size
  override on the fiscal Arabic receipt (with QR).
"""
import base64

from sqlalchemy import select

from conftest import add_product, auth_headers, make_client_account
from core.database import db_manager
from models.clients import Clients

RASTER_CMD = b"\x1d\x76\x30"  # GS v 0 — the ESC/POS raster command


async def _set_vat(client_id: int, vat: str = "300000000000003"):
    async with db_manager.async_session_maker() as db:
        row = (await db.execute(select(Clients).where(Clients.id == client_id))).scalar_one()
        row.vat_number = vat
        await db.commit()


async def _register_receipt_printer(client, token, paper_size="58mm"):
    resp = await client.post(
        "/api/v1/printers",
        headers=auth_headers(token),
        json={
            "name": "Front",
            "role": "receipt",
            "is_default": True,
            "device_id": "usb:front",
            "paper_size": paper_size,
        },
    )
    assert resp.status_code == 201, resp.text


async def _open_ticket_with_line(client, token, client_id, user_id, price=40.0, qty=2):
    table_id = (
        await client.post(
            "/api/v1/restaurant/tables",
            json={"name": "P1", "seats": 4},
            headers=auth_headers(token),
        )
    ).json()["id"]
    ticket_id = (
        await client.post(
            "/api/v1/restaurant/order-tickets",
            json={"order_type": "dine_in", "table_id": table_id},
            headers=auth_headers(token),
        )
    ).json()["id"]
    pid = await add_product(client_id, user_id, name="Shawarma", quantity=50, price=price)
    await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/items",
        json={"product_id": pid, "qty": qty},
        headers=auth_headers(token),
    )
    return ticket_id


def _raster_width_bytes(b64: str) -> int:
    raw = base64.b64decode(b64)
    assert RASTER_CMD in raw, "an ESC/POS raster image must be present"
    idx = raw.index(RASTER_CMD)
    return raw[idx + 4] + (raw[idx + 5] << 8)


async def test_proforma_check_routes_to_receipt_printer(client):
    """The proforma carries the resolved receipt printer and honors its
    paper_size override, while staying a non-fiscal Arabic check."""
    user, token, client_id = await make_client_account(client, business_type="restaurant")
    await _register_receipt_printer(client, token, paper_size="58mm")
    ticket_id = await _open_ticket_with_line(client, token, client_id, user["id"])

    resp = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/check",
        json={},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Routing: the response tells the client which device to stream to.
    assert body["printer"] is not None
    assert body["printer"]["device_id"] == "usb:front"
    # 58mm printer drives the narrower 384-dot raster (vs the 80mm 576 default).
    assert _raster_width_bytes(body["proforma_base64"]) == 384 // 8
    # Still an always-Arabic, non-fiscal proforma — no QR.
    assert body["title_ar"] == "فاتورة مبدئية"
    assert body["has_qr"] is False


async def test_settle_receipt_routes_to_receipt_printer(client):
    """Settling a ticket carries the resolved receipt printer and honors its
    paper_size override on the fiscal Arabic receipt (with QR)."""
    user, token, client_id = await make_client_account(client, business_type="restaurant")
    await _set_vat(client_id)
    await _register_receipt_printer(client, token, paper_size="58mm")
    ticket_id = await _open_ticket_with_line(
        client, token, client_id, user["id"], price=100.0, qty=1
    )

    resp = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/settle",
        json={"payment_method": "cash"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Routing: the response tells the client which device to stream to.
    assert body["printer"] is not None
    assert body["printer"]["device_id"] == "usb:front"
    # 58mm printer drives the narrower 384-dot raster (vs the 80mm 576 default).
    assert _raster_width_bytes(body["receipt_base64"]) == 384 // 8
    # A fiscal receipt: a real ECDSA-stamped ZATCA QR is embedded.
    assert body["zatca_qr"]
