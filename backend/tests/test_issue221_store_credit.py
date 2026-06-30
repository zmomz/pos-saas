"""M5·CRM (#221) — per-customer store-credit ledger (tracer bullet).

Acceptance: "store credit accrues/spends via a ledger." A customer can be granted
store credit and later spend it; every movement is an auditable ledger row that
pins the signed amount and the resulting ``balance_after``, mirroring the gift-card
ledger pattern (``models/gift_card_ledger.py``). The server is authoritative: a
redemption can never overdraw the balance, and one tenant can neither read nor move
another tenant's customer credit (SEC-02 owner-scoping).
"""
from sqlalchemy import select

from conftest import auth_headers, make_client_account
from core.database import db_manager
from models.store_credit_ledger import StoreCreditLedger


async def _make_customer(client, token, name="Credit Cust"):
    resp = await client.post(
        "/api/v1/entities/customers", json={"name": name}, headers=auth_headers(token)
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _ledger_rows(customer_id: int):
    async with db_manager.async_session_maker() as db:
        rows = (
            await db.execute(
                select(StoreCreditLedger)
                .where(StoreCreditLedger.customer_id == customer_id)
                .order_by(StoreCreditLedger.id)
            )
        ).scalars().all()
        return [(r.entry_type, float(r.amount), float(r.balance_after)) for r in rows]


async def test_grant_accrues_store_credit_and_records_a_ledger_row(client):
    _, token, _ = await make_client_account(client)
    cust_id = await _make_customer(client, token)

    # No credit yet → zero balance, empty history.
    r0 = await client.get(
        f"/api/v1/entities/customers/{cust_id}/store-credit", headers=auth_headers(token)
    )
    assert r0.status_code == 200, r0.text
    assert r0.json()["balance"] == 0.0
    assert r0.json()["history"] == []

    # Grant 50.00 of store credit.
    r1 = await client.post(
        f"/api/v1/entities/customers/{cust_id}/store-credit",
        json={"entry_type": "grant", "amount": 50, "note": "goodwill"},
        headers=auth_headers(token),
    )
    assert r1.status_code == 201, r1.text
    assert r1.json()["balance"] == 50.0

    assert await _ledger_rows(cust_id) == [("grant", 50.0, 50.0)]


async def test_redeem_spends_credit_and_cannot_overdraw(client):
    _, token, _ = await make_client_account(client)
    cust_id = await _make_customer(client, token)

    await client.post(
        f"/api/v1/entities/customers/{cust_id}/store-credit",
        json={"entry_type": "grant", "amount": 50},
        headers=auth_headers(token),
    )

    # Spend 20 → balance 30.
    r = await client.post(
        f"/api/v1/entities/customers/{cust_id}/store-credit",
        json={"entry_type": "redeem", "amount": 20},
        headers=auth_headers(token),
    )
    assert r.status_code == 201, r.text
    assert r.json()["balance"] == 30.0

    # Overdraw attempt (spend 40 of 30 remaining) is rejected and books nothing.
    over = await client.post(
        f"/api/v1/entities/customers/{cust_id}/store-credit",
        json={"entry_type": "redeem", "amount": 40},
        headers=auth_headers(token),
    )
    assert over.status_code == 400, over.text

    # Ledger holds only the grant and the valid redeem; redeem is signed negative.
    assert await _ledger_rows(cust_id) == [
        ("grant", 50.0, 50.0),
        ("redeem", -20.0, 30.0),
    ]

    # Balance endpoint agrees and returns the full history newest-last.
    bal = await client.get(
        f"/api/v1/entities/customers/{cust_id}/store-credit", headers=auth_headers(token)
    )
    assert bal.json()["balance"] == 30.0
    assert len(bal.json()["history"]) == 2


async def test_store_credit_is_owner_scoped(client):
    _, token_a, _ = await make_client_account(client)
    _, token_b, _ = await make_client_account(client)
    cust_id = await _make_customer(client, token_a)
    await client.post(
        f"/api/v1/entities/customers/{cust_id}/store-credit",
        json={"entry_type": "grant", "amount": 25},
        headers=auth_headers(token_a),
    )

    # Tenant B cannot read tenant A's customer credit …
    read = await client.get(
        f"/api/v1/entities/customers/{cust_id}/store-credit", headers=auth_headers(token_b)
    )
    assert read.status_code == 404, read.text

    # … nor move it.
    move = await client.post(
        f"/api/v1/entities/customers/{cust_id}/store-credit",
        json={"entry_type": "grant", "amount": 999},
        headers=auth_headers(token_b),
    )
    assert move.status_code == 404, move.text

    # Tenant A's balance is untouched by B's attempts.
    bal = await client.get(
        f"/api/v1/entities/customers/{cust_id}/store-credit", headers=auth_headers(token_a)
    )
    assert bal.json()["balance"] == 25.0
