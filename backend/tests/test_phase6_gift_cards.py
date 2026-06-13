"""CRM-03 / PRC-05 — gift cards / store credit redeemed as a tender (F-038).

Proves the end-to-end loop the finding names: issue a prepaid gift card, redeem it
as a sale *tender*, and see its balance decremented atomically. Also pins the
guards that make it safe: an insufficient/expired card blocks the sale and persists
nothing, and one client can neither see, look up, nor redeem another client's card
(SEC-02 owner-scoping).
"""
from datetime import datetime, timedelta

from sqlalchemy import func, select

from conftest import (
    add_product,
    auth_headers,
    make_client_account,
)
from core.database import db_manager
from models.gift_cards import Gift_cards
from models.payment_tenders import PaymentTenders
from models.transactions import Transactions


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _issue_card(client, token, amount, expiry_date=None):
    payload = {"amount": amount}
    if expiry_date is not None:
        payload["expiry_date"] = expiry_date
    resp = await client.post(
        "/api/v1/gift-cards", json=payload, headers=auth_headers(token)
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _card_balance(card_id: int) -> float:
    async with db_manager.async_session_maker() as db:
        return (
            await db.execute(select(Gift_cards.balance).where(Gift_cards.id == card_id))
        ).scalar_one()


async def _card_status(card_id: int) -> str:
    async with db_manager.async_session_maker() as db:
        return (
            await db.execute(select(Gift_cards.status).where(Gift_cards.id == card_id))
        ).scalar_one()


async def _txn_count(client_id: int) -> int:
    async with db_manager.async_session_maker() as db:
        return (
            await db.execute(
                select(func.count(Transactions.id)).where(
                    Transactions.client_id == client_id
                )
            )
        ).scalar() or 0


async def _tenders_for_txn(txn_id: int):
    async with db_manager.async_session_maker() as db:
        rows = (
            await db.execute(
                select(PaymentTenders).where(PaymentTenders.transaction_id == txn_id)
            )
        ).scalars().all()
        return [{"tender_type": r.tender_type, "amount": r.amount, "gateway": r.gateway,
                 "last4": r.last4, "gateway_ref": r.gateway_ref} for r in rows]


# ---------------------------------------------------------------------------
# F-038 model invariant: a gift card never stores a PAN (it isn't a card)
# ---------------------------------------------------------------------------
def test_gift_card_schema_has_balance_and_status_no_pan():
    cols = set(Gift_cards.__table__.columns.keys())
    for required in ("code", "balance", "initial_balance", "status", "expiry_date"):
        assert required in cols, f"gift_cards missing {required}"
    for forbidden in ("pan", "card_number"):
        assert forbidden not in cols


# ---------------------------------------------------------------------------
# CRM-03/PRC-05: issue a gift card, redeem as a tender, balance decremented
# ---------------------------------------------------------------------------
async def test_gift_card_issue_then_redeem_decrements_balance(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Mug", quantity=10, price=100.0)

    card = await _issue_card(client, token, 200.0)
    assert card["balance"] == 200.0
    assert card["status"] == "active"
    assert card["code"].startswith("GC-")

    # One @ 100 + 15% VAT = 115.00, paid entirely by the gift card.
    resp = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Mug", "price": 100.0, "quantity": 1}],
            "payment_method": "giftcard",
            "payment_gift_card_code": card["code"],
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_amount"] == 115.0

    # The sale carries a giftcard tender (no gateway, no PAN, last4 only).
    tenders = await _tenders_for_txn(body["id"])
    assert len(tenders) == 1
    gc = tenders[0]
    assert gc["tender_type"] == "giftcard"
    assert gc["amount"] == 115.0
    assert gc["gateway"] == "giftcard"
    assert gc["gateway_ref"] == f"giftcard:{card['id']}"
    assert gc["last4"] == card["code"][-4:]

    # Balance decremented by exactly the redeemed amount; card still active.
    assert await _card_balance(card["id"]) == 85.0
    assert await _card_status(card["id"]) == "active"


async def test_gift_card_redeem_to_zero_marks_redeemed(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Plate", quantity=10, price=100.0)

    card = await _issue_card(client, token, 115.0)  # exactly the sale total
    resp = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Plate", "price": 100.0, "quantity": 1}],
            "payment_method": "giftcard",
            "payment_gift_card_code": card["code"],
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert await _card_balance(card["id"]) == 0.0
    assert await _card_status(card["id"]) == "redeemed"


# ---------------------------------------------------------------------------
# Guard: an insufficient card blocks the sale and persists nothing
# ---------------------------------------------------------------------------
async def test_gift_card_insufficient_balance_blocks_sale_and_persists_nothing(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Lamp", quantity=10, price=100.0)

    card = await _issue_card(client, token, 5.0)  # nowhere near the 115 total
    assert await _txn_count(client_id) == 0

    resp = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Lamp", "price": 100.0, "quantity": 1}],
            "payment_method": "giftcard",
            "payment_gift_card_code": card["code"],
        },
        headers=headers,
    )
    assert resp.status_code == 400, resp.text
    # Nothing committed: no transaction, no tender, balance untouched, stock intact.
    assert await _txn_count(client_id) == 0
    assert await _card_balance(card["id"]) == 5.0


# ---------------------------------------------------------------------------
# Guard: an expired card is rejected
# ---------------------------------------------------------------------------
async def test_expired_gift_card_rejected(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Clock", quantity=10, price=100.0)

    past = (datetime.now() - timedelta(days=1)).replace(microsecond=0).isoformat()
    card = await _issue_card(client, token, 500.0, expiry_date=past)

    resp = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Clock", "price": 100.0, "quantity": 1}],
            "payment_method": "giftcard",
            "payment_gift_card_code": card["code"],
        },
        headers=headers,
    )
    assert resp.status_code == 400, resp.text
    assert "expired" in resp.json()["detail"].lower()
    assert await _card_balance(card["id"]) == 500.0  # untouched


# ---------------------------------------------------------------------------
# Balance endpoint + owner scoping (SEC-02)
# ---------------------------------------------------------------------------
async def test_gift_card_balance_endpoint(client):
    _user, token, _client_id = await make_client_account(client)
    card = await _issue_card(client, token, 75.0)

    resp = await client.get(
        f"/api/v1/gift-cards/{card['code']}/balance", headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["balance"] == 75.0
    assert body["status"] == "active"
    assert body["is_redeemable"] is True


async def test_gift_card_is_owner_scoped(client):
    user_a, token_a, client_a = await make_client_account(client)
    pid_a = await add_product(client_a, user_a["id"], name="A-Widget", quantity=5, price=100.0)
    card = await _issue_card(client, token_a, 300.0)

    # A second, unrelated client.
    _user_b, token_b, _client_b = await make_client_account(client)

    # B cannot see A's card in their list...
    listed = await client.get("/api/v1/gift-cards", headers=auth_headers(token_b))
    assert listed.status_code == 200, listed.text
    assert all(c["code"] != card["code"] for c in listed.json()["items"])

    # ...cannot look up its balance (foreign code → 404)...
    bal = await client.get(
        f"/api/v1/gift-cards/{card['code']}/balance", headers=auth_headers(token_b)
    )
    assert bal.status_code == 404, bal.text

    # ...and cannot redeem it on a sale (invalid in B's scope → 400), and A's
    # card balance is untouched by the attempt.
    pid_b = await add_product(_client_b, _user_b["id"], name="B-Widget", quantity=5, price=100.0)
    resp = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid_b, "name": "B-Widget", "price": 100.0, "quantity": 1}],
            "payment_method": "giftcard",
            "payment_gift_card_code": card["code"],
        },
        headers=auth_headers(token_b),
    )
    assert resp.status_code == 400, resp.text
    assert await _card_balance(card["id"]) == 300.0


# ---------------------------------------------------------------------------
# Split tender: cash + gift card, only the gift-card leg touches the card
# ---------------------------------------------------------------------------
async def test_split_cash_plus_gift_card(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Combo", quantity=10, price=100.0)

    card = await _issue_card(client, token, 100.0)
    # Total 115: 50 gift card + 65 cash.
    resp = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Combo", "price": 100.0, "quantity": 1}],
            "payment_method": "mixed",
            "payments": [
                {"method": "giftcard", "amount": 50.0, "gift_card_code": card["code"]},
                {"method": "cash", "amount": 65.0},
            ],
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    tenders = {t["tender_type"]: t for t in await _tenders_for_txn(body["id"])}
    assert tenders["giftcard"]["amount"] == 50.0
    assert tenders["cash"]["amount"] == 65.0
    # Only the gift-card portion is drawn down.
    assert await _card_balance(card["id"]) == 50.0
    # The stored breakdown redacts the bearer code (last 4 only).
    assert card["code"] not in (body.get("payment_breakdown") or "")
