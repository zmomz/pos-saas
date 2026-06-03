"""PAY-01/05/09 — Saudi-real tender capture on the sale path (F-001/F-002/F-003).

Proves that a card-like tender (Mada/card/wallet/BNPL) must obtain a real gateway
approval before a sale can complete: a DECLINE returns 4xx and persists **nothing**
(no transaction, no stock movement, no tender), while an APPROVE records a tender
carrying the network + approval code + RRN. Also pins the PCI invariant (the
tender model has no PAN column) and the Saudi tender taxonomy.
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
from services.payment_gateway import (
    CARD_LIKE_TENDERS,
    SUPPORTED_TENDER_TYPES,
    SandboxGateway,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _txn_count(client_id: int) -> int:
    async with db_manager.async_session_maker() as db:
        return (
            await db.execute(
                select(func.count(Transactions.id)).where(Transactions.client_id == client_id)
            )
        ).scalar() or 0


async def _tenders_for_txn(txn_id: int):
    async with db_manager.async_session_maker() as db:
        rows = (
            await db.execute(
                select(PaymentTenders).where(PaymentTenders.transaction_id == txn_id)
            )
        ).scalars().all()
        return [
            {
                "tender_type": r.tender_type,
                "amount": r.amount,
                "network": r.network,
                "approval_code": r.approval_code,
                "rrn": r.rrn,
                "gateway_ref": r.gateway_ref,
                "last4": r.last4,
                "status": r.status,
                "gateway": r.gateway,
            }
            for r in rows
        ]


async def _tender_count(client_id: int) -> int:
    async with db_manager.async_session_maker() as db:
        return (
            await db.execute(
                select(func.count(PaymentTenders.id)).where(
                    PaymentTenders.client_id == client_id
                )
            )
        ).scalar() or 0


# ---------------------------------------------------------------------------
# F-003: the tender model stores no PAN (PCI scope minimization, PAY-09)
# ---------------------------------------------------------------------------
def test_payment_tenders_schema_carries_proof_but_no_pan():
    cols = set(PaymentTenders.__table__.columns.keys())
    # The capture proof must be present...
    for required in ("approval_code", "rrn", "network", "last4", "token", "gateway_ref"):
        assert required in cols, f"payment_tenders missing {required}"
    # ...and a full card number must never be modeled.
    for forbidden in ("pan", "card_number", "cardnumber", "card_no"):
        assert forbidden not in cols, f"payment_tenders must not store a PAN ({forbidden})"


# ---------------------------------------------------------------------------
# F-002: the Saudi tender taxonomy is first-class
# ---------------------------------------------------------------------------
def test_tender_type_enum_includes_saudi_tenders():
    saudi = {"mada", "applepay", "stcpay", "tabby", "tamara"}
    assert saudi.issubset(set(SUPPORTED_TENDER_TYPES))
    # All Saudi tenders require a real gateway approval; cash does not.
    assert saudi.issubset(CARD_LIKE_TENDERS)
    assert "cash" not in CARD_LIKE_TENDERS


async def test_tender_types_endpoint_lists_saudi_tenders(client):
    _user, token, _client_id = await make_client_account(client)
    resp = await client.get("/api/v1/payments/tender-types", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    for tt in ("mada", "applepay", "stcpay", "tabby", "tamara"):
        assert tt in body["tender_types"]
    # Default install is the credential-free sandbox gateway.
    assert body["gateway"] == "sandbox"


async def test_tender_types_endpoint_requires_auth(client):
    resp = await client.get("/api/v1/payments/tender-types")
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# F-001: a declined card tender blocks the sale and persists nothing
# ---------------------------------------------------------------------------
async def test_card_decline_blocks_sale_and_persists_nothing(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=5, price=10.0)

    assert await _txn_count(client_id) == 0

    resp = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Cola", "price": 10.0, "quantity": 2}],
            "payment_method": "mada",
            "payment_simulate": "decline",  # sandbox-forced decline
        },
        headers=headers,
    )
    # Decline → 402 Payment Required, nothing committed.
    assert resp.status_code == 402, resp.text
    assert await _txn_count(client_id) == 0
    assert await _tender_count(client_id) == 0
    # Stock untouched and the invoice counter not consumed.
    assert await get_product_quantity(pid) == 5


# ---------------------------------------------------------------------------
# F-001: an approved card tender captures the approval onto the invoice
# ---------------------------------------------------------------------------
async def test_card_approve_captures_approval_on_tender(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Juice", quantity=10, price=12.0)

    resp = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Juice", "price": 12.0, "quantity": 1}],
            "payment_method": "mada",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Response surfaces the captured tender with a real approval.
    assert body["tenders"], "sale response should carry captured tenders"
    tender = body["tenders"][0]
    assert tender["tender_type"] == "mada"
    assert tender["network"] == "MADA"
    assert tender["approval_code"]

    # And it is persisted (PCI-safe: approval/rrn present, no PAN anywhere).
    persisted = await _tenders_for_txn(body["id"])
    assert len(persisted) == 1
    row = persisted[0]
    assert row["tender_type"] == "mada"
    assert row["approval_code"] is not None
    assert row["rrn"] is not None
    assert row["network"] == "MADA"
    assert row["status"] == "captured"
    assert row["gateway"] == "sandbox"


async def test_cash_sale_records_tender_without_gateway_approval(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Water", quantity=10, price=2.0)

    resp = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Water", "price": 2.0, "quantity": 3}],
            "payment_method": "cash",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    persisted = await _tenders_for_txn(body["id"])
    assert len(persisted) == 1
    assert persisted[0]["tender_type"] == "cash"
    # Cash settles internally — no gateway approval is captured.
    assert persisted[0]["approval_code"] is None


# ---------------------------------------------------------------------------
# Split tenders: each card-like leg captures its own approval
# ---------------------------------------------------------------------------
async def test_split_card_plus_cash_captures_only_card_leg(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Combo", quantity=10, price=100.0)

    # One unit @ 100 + 15% VAT = 115.00; split 100 mada + 15 cash.
    resp = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Combo", "price": 100.0, "quantity": 1}],
            "payment_method": "mixed",
            "payments": [
                {"method": "mada", "amount": 100.0},
                {"method": "cash", "amount": 15.0},
            ],
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    persisted = {t["tender_type"]: t for t in await _tenders_for_txn(body["id"])}
    assert persisted["mada"]["approval_code"] is not None
    assert persisted["cash"]["approval_code"] is None


# ---------------------------------------------------------------------------
# F-002: the standalone capture endpoint exists (terminal/online pre-auth)
# ---------------------------------------------------------------------------
async def test_charge_endpoint_declines_then_approves(client):
    _user, token, _client_id = await make_client_account(client)
    headers = auth_headers(token)

    declined = await client.post(
        "/api/v1/payments/charge",
        json={"tender_type": "mada", "amount": 50.0, "simulate": "decline"},
        headers=headers,
    )
    assert declined.status_code == 402, declined.text

    approved = await client.post(
        "/api/v1/payments/charge",
        json={"tender_type": "mada", "amount": 50.0},
        headers=headers,
    )
    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert body["approved"] is True
    assert body["approval_code"]
    assert body["tender_id"]
    assert body["status"] == "authorized"


async def test_charge_endpoint_rejects_cash(client):
    _user, token, _client_id = await make_client_account(client)
    headers = auth_headers(token)
    resp = await client.post(
        "/api/v1/payments/charge",
        json={"tender_type": "cash", "amount": 50.0},
        headers=auth_headers(token),
    )
    assert resp.status_code == 400, resp.text


# ---------------------------------------------------------------------------
# F-004 / PAY-10: refunds route back to the original tender
# ---------------------------------------------------------------------------
async def _open_shift(client, headers, opening_cash=100.0):
    resp = await client.post(
        "/api/v1/production/shifts/open",
        json={"opening_cash": opening_cash},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_card_refund_routes_to_origin_and_not_the_drawer(client):
    """F-004 / PAY-10: refunding a card sale reverses the charge through the
    capturing gateway — a ``refunded`` tender on the credit note carries the
    gateway refund reference (sandbox ``rfnd_…``) — and the money does NOT come
    out of the cash drawer (only a cash refund is cash paid out)."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Combo", quantity=10, price=100.0)

    await _open_shift(client, headers, opening_cash=100.0)

    # 1 unit @ 100 + 15% VAT = 115.00 paid by Mada.
    sale = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Combo", "price": 100.0, "quantity": 1}],
            "payment_method": "mada",
        },
        headers=headers,
    )
    assert sale.status_code == 200, sale.text
    sale_id = sale.json()["id"]

    refund = await client.post(
        f"/api/v1/pos/transactions/{sale_id}/refund", headers=headers
    )
    assert refund.status_code == 200, refund.text
    credit_id = refund.json()["credit_note_id"]

    # The refund is routed back to the card: a `refunded` tender on the credit note
    # carries the gateway refund handle, proving gateway.refund(tender_ref) ran.
    refunded = await _tenders_for_txn(credit_id)
    assert len(refunded) == 1, refunded
    r = refunded[0]
    assert r["tender_type"] == "mada"
    assert r["status"] == "refunded"
    assert r["gateway"] == "sandbox"
    assert r["network"] == "MADA"
    assert (r["gateway_ref"] or "").startswith("rfnd_")
    assert abs(r["amount"] - 115.0) < 0.01

    # The card refund did NOT debit the cash drawer.
    x = (await client.get("/api/v1/reports/zreport", headers=headers)).json()
    assert abs(x["cash"]["cash_refunds"]) < 0.01
    # opening 100 only — no cash ever moved (the sale was card, the refund a reversal).
    assert abs(x["cash"]["expected_cash"] - 100.0) < 0.01


async def test_cash_refund_is_recorded_and_still_debits_the_drawer(client):
    """A cash refund has no gateway leg but is still recorded as a ``refunded``
    cash tender and remains cash paid out of the drawer (F-004 must not change the
    cash-refund drawer math, only the card-refund math)."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=50, price=10.0)

    await _open_shift(client, headers, opening_cash=100.0)

    # 2 @ 10 + 15% = 23.00 cash.
    sale = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Cola", "price": 10.0, "quantity": 2}],
            "payment_method": "cash",
        },
        headers=headers,
    )
    assert sale.status_code == 200, sale.text
    sale_id = sale.json()["id"]

    refund = await client.post(
        f"/api/v1/pos/transactions/{sale_id}/refund", headers=headers
    )
    assert refund.status_code == 200, refund.text
    credit_id = refund.json()["credit_note_id"]

    refunded = await _tenders_for_txn(credit_id)
    assert len(refunded) == 1, refunded
    r = refunded[0]
    assert r["tender_type"] == "cash"
    assert r["status"] == "refunded"
    # Cash settles internally — no gateway reversal handle.
    assert not (r["gateway_ref"] or "").startswith("rfnd_")
    assert abs(r["amount"] - 23.0) < 0.01

    # The cash refund IS cash out of the drawer: opening 100 + cash 23 − refund 23.
    x = (await client.get("/api/v1/reports/zreport", headers=headers)).json()
    assert abs(x["cash"]["cash_refunds"] - 23.0) < 0.01
    assert abs(x["cash"]["expected_cash"] - 100.0) < 0.01


async def test_partial_card_refund_reverses_only_the_returned_share(client):
    """A partial (line-level) refund of a card sale reverses only the returned
    units' share back to the card (POS-07 × PAY-10)."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Combo", quantity=10, price=100.0)

    # 2 units @ 100 + 15% VAT = 230.00 paid by Mada.
    sale = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Combo", "price": 100.0, "quantity": 2}],
            "payment_method": "mada",
        },
        headers=headers,
    )
    assert sale.status_code == 200, sale.text
    sale_id = sale.json()["id"]

    # Return only 1 of the 2 units → half the invoice → 115.00 reversed to the card.
    refund = await client.post(
        f"/api/v1/pos/transactions/{sale_id}/refund",
        json={"lines": [{"product_id": pid, "quantity": 1}]},
        headers=headers,
    )
    assert refund.status_code == 200, refund.text
    body = refund.json()
    assert body["original_status"] == "partial_refunded"

    refunded = await _tenders_for_txn(body["credit_note_id"])
    assert len(refunded) == 1, refunded
    assert refunded[0]["tender_type"] == "mada"
    assert refunded[0]["status"] == "refunded"
    assert (refunded[0]["gateway_ref"] or "").startswith("rfnd_")
    assert abs(refunded[0]["amount"] - 115.0) < 0.01


# ---------------------------------------------------------------------------
# Sandbox gateway unit behavior
# ---------------------------------------------------------------------------
async def test_sandbox_gateway_approve_and_decline():
    gw = SandboxGateway()
    ok = await gw.charge(23.0, "mada")
    assert ok.approved and ok.approval_code and ok.rrn and ok.network == "MADA"
    no = await gw.charge(23.0, "mada", simulate="decline")
    assert not no.approved and no.decline_reason


async def test_sandbox_gateway_refund_returns_a_handle():
    gw = SandboxGateway()
    res = await gw.refund("sbx_deadbeef", 50.0)
    assert res.approved and res.gateway == "sandbox"
    assert (res.gateway_ref or "").startswith("rfnd_")
