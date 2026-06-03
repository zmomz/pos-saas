"""Phase 5 — Hardware: integrated SoftPOS terminal + cash-drawer kick (F-005).

Two halves of F-005:

* **HW-03 (PAY-05)** — an integrated in-store terminal captures a *real* approval.
  A merchant registers a paired Geidea SoftPOS terminal, then a card-like tender is
  pushed to it: APPROVE captures network/approval/RRN as an ``authorized`` tender;
  DECLINE returns 402 and persists nothing (so a terminal decline blocks the sale).
  Routing a sale's card leg to the terminal captures via the ``geidea`` adapter and
  a declined terminal rolls the whole sale back. Terminals are owner-scoped (SEC-02).

* **HW-04** — a cash sale's ESC/POS byte stream carries the ``0x1B 0x70`` drawer-kick
  pulse so a connected till opens; a card sale's does not.
"""
from sqlalchemy import func, select

from conftest import (
    add_product,
    auth_headers,
    get_product_quantity,
    make_client_account,
)
from core.database import db_manager
from models.payment_tenders import PaymentTenders
from models.transactions import Transactions
from services.escpos import build_receipt
from services.payment_gateway import GeideaTerminalGateway, get_terminal_gateway


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _tender_count(client_id: int) -> int:
    async with db_manager.async_session_maker() as db:
        return (
            await db.execute(
                select(func.count(PaymentTenders.id)).where(
                    PaymentTenders.client_id == client_id
                )
            )
        ).scalar() or 0


async def _txn_count(client_id: int) -> int:
    async with db_manager.async_session_maker() as db:
        return (
            await db.execute(
                select(func.count(Transactions.id)).where(Transactions.client_id == client_id)
            )
        ).scalar() or 0


async def _register_terminal(client, headers, **kwargs):
    payload = {"provider": "geidea", "label": "Till-1", "serial": "GEI-001"}
    payload.update(kwargs)
    resp = await client.post("/api/v1/payments/terminals", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# HW-03: terminal register + capture
# ---------------------------------------------------------------------------
async def test_register_and_charge_terminal_captures_approval(client):
    _user, token, _cid = await make_client_account(client)
    headers = auth_headers(token)
    terminal = await _register_terminal(client, headers)
    assert terminal["provider"] == "geidea"
    assert terminal["status"] == "active"

    charged = await client.post(
        "/api/v1/payments/terminal/charge",
        json={"terminal_id": terminal["id"], "amount": 57.5, "tender_type": "mada"},
        headers=headers,
    )
    assert charged.status_code == 200, charged.text
    body = charged.json()
    # A real (sandbox-simulated) in-store approval: network + approval + RRN, no PAN.
    assert body["approved"] is True
    assert body["gateway"] == "geidea"
    assert body["network"] == "MADA"
    assert body["approval_code"]
    assert body["rrn"]
    assert body["status"] == "authorized"


async def test_terminal_charge_decline_returns_402_and_persists_nothing(client):
    _user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    terminal = await _register_terminal(client, headers)

    assert await _tender_count(client_id) == 0
    declined = await client.post(
        "/api/v1/payments/terminal/charge",
        json={"terminal_id": terminal["id"], "amount": 40.0, "simulate": "decline"},
        headers=headers,
    )
    assert declined.status_code == 402, declined.text
    # A terminal decline persists no tender (so the sale that needs it cannot complete).
    assert await _tender_count(client_id) == 0


async def test_terminal_charge_is_owner_scoped(client):
    _u1, token1, _c1 = await make_client_account(client)
    _u2, token2, _c2 = await make_client_account(client)
    terminal = await _register_terminal(client, auth_headers(token1))

    # The second client must not be able to charge the first client's terminal.
    resp = await client.post(
        "/api/v1/payments/terminal/charge",
        json={"terminal_id": terminal["id"], "amount": 10.0},
        headers=auth_headers(token2),
    )
    assert resp.status_code == 404, resp.text


async def test_terminal_charge_rejects_cash(client):
    _user, token, _cid = await make_client_account(client)
    headers = auth_headers(token)
    terminal = await _register_terminal(client, headers)
    resp = await client.post(
        "/api/v1/payments/terminal/charge",
        json={"terminal_id": terminal["id"], "amount": 10.0, "tender_type": "cash"},
        headers=headers,
    )
    assert resp.status_code == 400, resp.text


async def test_register_terminal_rejects_unknown_provider(client):
    _user, token, _cid = await make_client_account(client)
    resp = await client.post(
        "/api/v1/payments/terminals",
        json={"provider": "nonsense"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 400, resp.text


# ---------------------------------------------------------------------------
# HW-03: routing a sale's card leg to the terminal (atomic capture/rollback)
# ---------------------------------------------------------------------------
async def test_sale_routed_to_terminal_captures_via_geidea(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    terminal = await _register_terminal(client, headers)
    pid = await add_product(client_id, user["id"], name="Juice", quantity=10, price=12.0)

    sale = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Juice", "price": 12.0, "quantity": 1}],
            "payment_method": "mada",
            "payment_terminal_id": terminal["id"],
        },
        headers=headers,
    )
    assert sale.status_code == 200, sale.text
    tenders = sale.json()["tenders"]
    assert tenders, "the sale should carry the captured terminal tender"
    assert tenders[0]["tender_type"] == "mada"
    assert tenders[0]["gateway"] == "geidea"
    assert tenders[0]["network"] == "MADA"


async def test_sale_with_declined_terminal_rolls_back(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    terminal = await _register_terminal(client, headers)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=5, price=10.0)

    assert await _txn_count(client_id) == 0
    sale = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Cola", "price": 10.0, "quantity": 2}],
            "payment_method": "mada",
            "payment_terminal_id": terminal["id"],
            "payment_simulate": "decline",
        },
        headers=headers,
    )
    assert sale.status_code == 402, sale.text
    # Nothing committed: no transaction, stock untouched.
    assert await _txn_count(client_id) == 0
    assert await get_product_quantity(pid) == 5


async def test_sale_with_unknown_terminal_is_rejected(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Water", quantity=5, price=2.0)
    sale = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Water", "price": 2.0, "quantity": 1}],
            "payment_method": "mada",
            "payment_terminal_id": 999999,
        },
        headers=headers,
    )
    assert sale.status_code == 400, sale.text
    assert await _txn_count(client_id) == 0


# ---------------------------------------------------------------------------
# HW-03: gateway adapter unit behaviour
# ---------------------------------------------------------------------------
async def test_geidea_terminal_gateway_approve_decline_refund():
    gw = get_terminal_gateway("geidea")
    assert isinstance(gw, GeideaTerminalGateway)
    # No live key in tests → deterministic sandbox simulation.
    assert gw.live is False

    ok = await gw.charge(50.0, "mada")
    assert ok.approved and ok.gateway == "geidea" and ok.network == "MADA"
    assert ok.approval_code and ok.rrn and (ok.gateway_ref or "").startswith("geidea_sbx_")

    no = await gw.charge(50.0, "mada", simulate="decline")
    assert not no.approved and no.decline_reason

    rf = await gw.refund(ok.gateway_ref, 50.0)
    assert rf.approved and (rf.gateway_ref or "").startswith("rfnd_")


# ---------------------------------------------------------------------------
# HW-04: the named test — cash-sale ESC/POS contains the drawer-kick bytes
# ---------------------------------------------------------------------------
def test_build_receipt_emits_drawer_kick_only_when_open_drawer():
    kwargs = dict(
        seller_name="Shop",
        vat_number="300000000000003",
        invoice_number="INV-0001-000001",
        issue_date="2026-06-03 10:00",
        line_items=[{"name": "Cola", "quantity": 1, "price": 10.0}],
        subtotal=10.0,
        discount=0.0,
        vat_amount=1.5,
        total_amount=11.5,
        zatca_qr="",
    )
    with_kick = build_receipt(open_drawer=True, **kwargs)
    without_kick = build_receipt(open_drawer=False, **kwargs)
    # The kick pulse (ESC p) is emitted deterministically right after the ESC @
    # init (bytes 0-1). Check that exact position rather than `in` — the Arabic
    # raster body (F-021) embeds arbitrary bitmap bytes that could otherwise
    # contain the 0x1B 0x70 sequence by chance.
    assert with_kick[2:4] == bytes([0x1B, 0x70])
    assert without_kick[2:4] != bytes([0x1B, 0x70])


async def test_cash_sale_escpos_contains_drawer_kick_bytes(client):
    """The finding's catch-forever: a cash sale's ESC/POS output kicks the drawer."""
    import base64

    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Water", quantity=10, price=2.0)

    sale = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Water", "price": 2.0, "quantity": 3}],
            "payment_method": "cash",
        },
        headers=headers,
    )
    assert sale.status_code == 200, sale.text
    txn_id = sale.json()["id"]

    resp = await client.get(f"/api/v1/pos/transactions/{txn_id}/escpos", headers=headers)
    assert resp.status_code == 200, resp.text
    raw = base64.b64decode(resp.json()["data"])
    # The kick pulse is emitted right after the ESC @ init; check that position
    # (the Arabic raster body, F-021, may contain 0x1B 0x70 as bitmap data).
    assert raw[2:4] == bytes([0x1B, 0x70]), "cash sale must pulse the cash-drawer kick (HW-04)"


async def test_card_sale_escpos_has_no_drawer_kick(client):
    import base64

    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Juice", quantity=10, price=12.0)

    sale = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Juice", "price": 12.0, "quantity": 1}],
            "payment_method": "mada",
        },
        headers=headers,
    )
    assert sale.status_code == 200, sale.text
    txn_id = sale.json()["id"]

    resp = await client.get(f"/api/v1/pos/transactions/{txn_id}/escpos", headers=headers)
    assert resp.status_code == 200, resp.text
    raw = base64.b64decode(resp.json()["data"])
    # No kick pulse at the deterministic init position (a card sale must not open
    # the drawer). Checked by position, not `in`, because the Arabic raster body
    # (F-021) may embed the 0x1B 0x70 byte pair as bitmap data.
    assert raw[2:4] != bytes([0x1B, 0x70]), "a non-cash sale must not kick the drawer"
