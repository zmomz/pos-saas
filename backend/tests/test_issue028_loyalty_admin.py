"""ISSUE-028 — loyalty admin: the four endpoints the LoyaltyProgram page calls.

The page hits ``/loyalty/config`` (GET+POST), ``/loyalty/balances``,
``/loyalty/transactions`` and ``/loyalty/adjust`` — none existed, so every load
was a swallowed 404. These cover the real round-trips.
"""
import pytest

from conftest import auth_headers, make_client_account
from core.database import db_manager
from models.customers import Customers


async def _add_customer(user_id: str, client_id: int, name: str = "Acme Co") -> int:
    async with db_manager.async_session_maker() as db:
        cust = Customers(user_id=user_id, name=name)
        db.add(cust)
        await db.commit()
        await db.refresh(cust)
        return cust.id


@pytest.mark.asyncio
async def test_config_save_persists_and_reloads(client):
    """POST /loyalty/config persists; GET reloads the saved values [AC1]."""
    user, token, client_id = await make_client_account(client)

    save = await client.post(
        "/api/v1/production/loyalty/config",
        headers=auth_headers(token),
        json={
            "points_per_sar": 2.0,
            "redemption_rate": 0.25,
            "min_points_redeem": 50,
            "is_active": True,
        },
    )
    assert save.status_code == 200, save.text

    reload = await client.get(
        "/api/v1/production/loyalty/config",
        headers=auth_headers(token),
    )
    assert reload.status_code == 200, reload.text
    body = reload.json()
    assert body["points_per_sar"] == 2.0
    assert body["redemption_rate"] == 0.25
    assert body["min_points_redeem"] == 50
    assert body["is_active"] is True


@pytest.mark.asyncio
async def test_balances_render_real_data(client):
    """GET /loyalty/balances returns owner-scoped rows with the customer name [AC2]."""
    user, token, client_id = await make_client_account(client)
    cust_id = await _add_customer(user["id"], client_id, name="Acme Co")

    # Earn some points for this customer via the existing earn endpoint.
    earn = await client.post(
        "/api/v1/production/loyalty/earn",
        headers=auth_headers(token),
        json={"customer_id": cust_id, "transaction_amount": 100.0, "points_rate": 1.0},
    )
    assert earn.status_code == 200, earn.text

    resp = await client.get(
        "/api/v1/production/loyalty/balances",
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 1
    row = body["items"][0]
    assert row["customer_id"] == cust_id
    assert row["customer_name"] == "Acme Co"
    assert row["points_balance"] == 100
    assert row["total_earned"] == 100


@pytest.mark.asyncio
async def test_balances_are_owner_scoped(client):
    """A merchant never sees another merchant's loyalty balances (SEC-02) [AC2]."""
    user_a, token_a, client_a = await make_client_account(client)
    cust_a = await _add_customer(user_a["id"], client_a, name="A Customer")
    await client.post(
        "/api/v1/production/loyalty/earn",
        headers=auth_headers(token_a),
        json={"customer_id": cust_a, "transaction_amount": 10.0, "points_rate": 1.0},
    )

    user_b, token_b, client_b = await make_client_account(client)
    resp = await client.get(
        "/api/v1/production/loyalty/balances",
        headers=auth_headers(token_b),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_adjust_add_changes_balance_and_writes_ledger(client):
    """POST /loyalty/adjust 'add' credits the balance and records a ledger entry [AC2]."""
    user, token, client_id = await make_client_account(client)
    cust_id = await _add_customer(user["id"], client_id, name="Bob")

    resp = await client.post(
        "/api/v1/production/loyalty/adjust",
        headers=auth_headers(token),
        json={"customer_id": cust_id, "type": "add", "points": 30, "reason": "goodwill"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["points_balance"] == 30

    # Ledger entry shows up in the history feed.
    tx = await client.get(
        "/api/v1/production/loyalty/transactions",
        headers=auth_headers(token),
    )
    assert tx.status_code == 200, tx.text
    body = tx.json()
    assert body["total"] == 1
    entry = body["items"][0]
    assert entry["type"] == "add"
    assert entry["points"] == 30
    assert entry["description"] == "goodwill"
    assert entry["customer_name"] == "Bob"

    # Balance is reflected in the balances feed too.
    bal = await client.get(
        "/api/v1/production/loyalty/balances",
        headers=auth_headers(token),
    )
    assert bal.json()["items"][0]["points_balance"] == 30


@pytest.mark.asyncio
async def test_adjust_deduct_cannot_go_negative(client):
    """A deduct beyond the balance is rejected (400), leaving the balance intact [AC2]."""
    user, token, client_id = await make_client_account(client)
    cust_id = await _add_customer(user["id"], client_id, name="Carol")
    await client.post(
        "/api/v1/production/loyalty/adjust",
        headers=auth_headers(token),
        json={"customer_id": cust_id, "type": "add", "points": 20},
    )

    resp = await client.post(
        "/api/v1/production/loyalty/adjust",
        headers=auth_headers(token),
        json={"customer_id": cust_id, "type": "deduct", "points": 50},
    )
    assert resp.status_code == 400
    assert "Insufficient" in resp.json()["detail"]

    bal = await client.get(
        "/api/v1/production/loyalty/balances",
        headers=auth_headers(token),
    )
    assert bal.json()["items"][0]["points_balance"] == 20


@pytest.mark.asyncio
async def test_transactions_are_owner_scoped(client):
    """The history feed never leaks another merchant's ledger entries (SEC-02) [AC2]."""
    user_a, token_a, client_a = await make_client_account(client)
    cust_a = await _add_customer(user_a["id"], client_a)
    await client.post(
        "/api/v1/production/loyalty/adjust",
        headers=auth_headers(token_a),
        json={"customer_id": cust_a, "type": "add", "points": 5},
    )

    user_b, token_b, client_b = await make_client_account(client)
    resp = await client.get(
        "/api/v1/production/loyalty/transactions",
        headers=auth_headers(token_b),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] == 0
