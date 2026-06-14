"""ISSUE-047 — saved/selected printer + per-station routing (H26/U5.2).

Behaviors:
- A merchant saves printers and selects a default; the selection persists and is
  single per role (AC1).
- ``resolve_printer`` routes a printable to the right printer: a station-bound
  KOT printer for that station, the role default otherwise, the newest printer as
  a last resort, and ``None`` when nothing is registered (AC3 — routing test).
- The /escpos receipt endpoint streams to (carries) the resolved default receipt
  printer and honors its paper_size override (AC2).
"""
import base64

import pytest

from conftest import auth_headers, make_client_account
from core.database import db_manager
from services.printers import PrintersService, resolve_printer

RASTER_CMD = b"\x1d\x76\x30"  # GS v 0 — the ESC/POS raster command


# ----------------------------- AC1: persistence ------------------------------
@pytest.mark.asyncio
async def test_saved_default_printer_persists(client):
    """A saved/selected default printer persists and is readable back (AC1)."""
    user, token, _ = await make_client_account(client)

    resp = await client.post(
        "/api/v1/printers",
        headers=auth_headers(token),
        json={"name": "Front", "role": "receipt", "is_default": True, "device_id": "usb:front"},
    )
    assert resp.status_code == 201, resp.text
    pid = resp.json()["id"]

    listed = await client.get("/api/v1/printers", headers=auth_headers(token))
    assert listed.status_code == 200
    rows = listed.json()
    assert len(rows) == 1
    assert rows[0]["id"] == pid
    assert rows[0]["is_default"] is True
    assert rows[0]["device_id"] == "usb:front"


@pytest.mark.asyncio
async def test_only_one_default_per_role(client):
    """Selecting a new default clears the previous one for that role (AC1)."""
    user, token, _ = await make_client_account(client)
    h = auth_headers(token)

    a = (await client.post("/api/v1/printers", headers=h,
                           json={"name": "A", "role": "receipt", "is_default": True})).json()
    b = (await client.post("/api/v1/printers", headers=h,
                           json={"name": "B", "role": "receipt", "is_default": True})).json()

    rows = {r["id"]: r for r in (await client.get("/api/v1/printers", headers=h)).json()}
    assert rows[a["id"]]["is_default"] is False
    assert rows[b["id"]]["is_default"] is True


@pytest.mark.asyncio
async def test_printers_owner_scoped(client):
    """A merchant never sees another merchant's printers (SEC-02)."""
    _, token_a, _ = await make_client_account(client)
    _, token_b, _ = await make_client_account(client)
    await client.post("/api/v1/printers", headers=auth_headers(token_a),
                      json={"name": "A-only", "role": "receipt"})

    rows_b = (await client.get("/api/v1/printers", headers=auth_headers(token_b))).json()
    assert rows_b == []


# ----------------------- AC3: routing resolution -----------------------------
@pytest.mark.asyncio
async def test_resolve_routes_kot_to_station_printer():
    """A KOT for a station routes to that station's bound printer (AC3)."""
    async with db_manager.async_session_maker() as db:
        svc = PrintersService(db)
        uid = "owner-route-1"
        await svc.create({"name": "Default KOT", "role": "kot", "is_default": True}, user_id=uid)
        grill = await svc.create({"name": "Grill", "role": "kot", "station_id": 7}, user_id=uid)

        chosen = await resolve_printer(db, uid, "kot", station_id=7)
        assert chosen is not None and chosen.id == grill.id


@pytest.mark.asyncio
async def test_resolve_falls_back_to_role_default():
    """No station match → the role's default printer (AC3)."""
    async with db_manager.async_session_maker() as db:
        svc = PrintersService(db)
        uid = "owner-route-2"
        default = await svc.create({"name": "Default KOT", "role": "kot", "is_default": True}, user_id=uid)
        await svc.create({"name": "Grill", "role": "kot", "station_id": 7}, user_id=uid)

        # station 99 has no bound printer → the general default wins
        chosen = await resolve_printer(db, uid, "kot", station_id=99)
        assert chosen is not None and chosen.id == default.id


@pytest.mark.asyncio
async def test_resolve_receipt_default():
    """A receipt routes to the default receipt printer, not a KOT printer (AC3)."""
    async with db_manager.async_session_maker() as db:
        svc = PrintersService(db)
        uid = "owner-route-3"
        await svc.create({"name": "Kitchen", "role": "kot", "is_default": True}, user_id=uid)
        front = await svc.create({"name": "Front", "role": "receipt", "is_default": True}, user_id=uid)

        chosen = await resolve_printer(db, uid, "receipt")
        assert chosen is not None and chosen.id == front.id


@pytest.mark.asyncio
async def test_resolve_none_when_nothing_registered():
    """No registered printer of the role → None (falls back to default path)."""
    async with db_manager.async_session_maker() as db:
        chosen = await resolve_printer(db, "owner-empty", "receipt")
        assert chosen is None


@pytest.mark.asyncio
async def test_resolve_ignores_inactive():
    """An inactive printer is never resolved (AC3)."""
    async with db_manager.async_session_maker() as db:
        svc = PrintersService(db)
        uid = "owner-route-4"
        await svc.create(
            {"name": "Broken", "role": "receipt", "is_default": True, "status": "inactive"},
            user_id=uid,
        )
        chosen = await resolve_printer(db, uid, "receipt")
        assert chosen is None


# --------------------- AC2: print path routes to printer ---------------------
async def _make_sale(client, token, user_id, client_id):
    from conftest import add_product

    pid = await add_product(client_id, user_id, quantity=10, price=10.0)
    sale = await client.post(
        "/api/v1/pos/transaction",
        headers=auth_headers(token),
        json={
            "items": [{"product_id": pid, "name": "Widget", "price": 10.0, "quantity": 1}],
            "payment_method": "cash",
        },
    )
    return sale.json()["id"]


@pytest.mark.asyncio
async def test_escpos_receipt_routes_to_default_printer(client):
    """The /escpos receipt carries the resolved default receipt printer and
    honors its paper_size override (AC2)."""
    user, token, client_id = await make_client_account(client)
    await client.post(
        "/api/v1/printers",
        headers=auth_headers(token),
        json={"name": "Front", "role": "receipt", "is_default": True,
              "device_id": "usb:front", "paper_size": "58mm"},
    )

    txn_id = await _make_sale(client, token, user["id"], client_id)
    resp = await client.get(
        f"/api/v1/pos/transactions/{txn_id}/escpos", headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # the response tells the client which device to stream to (routing)
    assert body["printer"] is not None
    assert body["printer"]["device_id"] == "usb:front"
    # 58mm override → 384-dot raster, narrower than the 80mm default (576)
    raw = base64.b64decode(body["data"])
    assert RASTER_CMD in raw
    idx = raw.index(RASTER_CMD)
    width_lo, width_hi = raw[idx + 4], raw[idx + 5]
    width_bytes = width_lo + (width_hi << 8)
    assert width_bytes == 384 // 8, "58mm printer must drive the 384-dot raster width"
