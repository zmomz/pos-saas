"""Phase E — loyalty accrual + redemption wired into the atomic POS sale."""
import pytest

from conftest import add_product, auth_headers, make_client_account
from core.database import db_manager
from models.loyalty_programs import Loyalty_programs


async def _seed_program(user_id: str, client_id: int, **kw):
    defaults = dict(
        points_per_sar=1.0,
        redemption_rate=0.5,
        min_redemption_points=10,
        is_active=True,
    )
    defaults.update(kw)
    async with db_manager.async_session_maker() as db:
        program = Loyalty_programs(
            user_id=user_id,
            client_id=client_id,
            name="Rewards",
            **defaults,
        )
        db.add(program)
        await db.commit()


async def _balance(client, token, customer_id: int) -> int:
    resp = await client.get(
        "/api/v1/production/loyalty/balance",
        params={"customer_id": customer_id},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["points_balance"]


@pytest.mark.asyncio
async def test_points_accrue_on_sale(client):
    user, token, client_id = await make_client_account(client)
    pid = await add_product(client_id, user["id"], quantity=100, price=100.0)
    await _seed_program(user["id"], client_id)

    resp = await client.post(
        "/api/v1/pos/transaction",
        headers=auth_headers(token),
        json={
            "items": [{"product_id": pid, "name": "Widget", "price": 100.0, "quantity": 1}],
            "payment_method": "cash",
            "customer_id": 1,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # subtotal 100 + 15% VAT = 115 total; 1 point/SAR => 115 earned.
    assert body["total_amount"] == 115.0
    assert body["loyalty_points_earned"] == 115
    assert body["loyalty_balance"] == 115
    assert body["loyalty_points_redeemed"] is None
    assert await _balance(client, token, 1) == 115


@pytest.mark.asyncio
async def test_redeem_points_as_discount(client):
    user, token, client_id = await make_client_account(client)
    pid = await add_product(client_id, user["id"], quantity=100, price=100.0)
    await _seed_program(user["id"], client_id)

    # First sale to build a balance of 115.
    await client.post(
        "/api/v1/pos/transaction",
        headers=auth_headers(token),
        json={
            "items": [{"product_id": pid, "name": "Widget", "price": 100.0, "quantity": 1}],
            "payment_method": "cash",
            "customer_id": 7,
        },
    )

    # Redeem 100 points (rate 0.5 SAR/pt => 50 SAR discount) on a 100 SAR order.
    resp = await client.post(
        "/api/v1/pos/transaction",
        headers=auth_headers(token),
        json={
            "items": [{"product_id": pid, "name": "Widget", "price": 100.0, "quantity": 1}],
            "payment_method": "cash",
            "customer_id": 7,
            "redeem_points": 100,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["loyalty_points_redeemed"] == 100
    assert body["loyalty_discount"] == 50.0
    # taxable 50 + 15% = 57.5 total
    assert body["total_amount"] == 57.5
    assert body["discount_amount"] == 50.0
    # 115 - 100 redeemed = 15, then accrue floor(57.5) = 57 => 72
    assert body["loyalty_points_earned"] == 57
    assert body["loyalty_balance"] == 72
    assert await _balance(client, token, 7) == 72


@pytest.mark.asyncio
async def test_redeem_requires_customer(client):
    user, token, client_id = await make_client_account(client)
    pid = await add_product(client_id, user["id"], quantity=10, price=10.0)
    await _seed_program(user["id"], client_id)

    resp = await client.post(
        "/api/v1/pos/transaction",
        headers=auth_headers(token),
        json={
            "items": [{"product_id": pid, "name": "W", "price": 10.0, "quantity": 1}],
            "payment_method": "cash",
            "redeem_points": 10,
        },
    )
    assert resp.status_code == 400
    assert "customer_id" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_redeem_insufficient_points(client):
    user, token, client_id = await make_client_account(client)
    pid = await add_product(client_id, user["id"], quantity=10, price=100.0)
    await _seed_program(user["id"], client_id)

    resp = await client.post(
        "/api/v1/pos/transaction",
        headers=auth_headers(token),
        json={
            "items": [{"product_id": pid, "name": "W", "price": 100.0, "quantity": 1}],
            "payment_method": "cash",
            "customer_id": 3,
            "redeem_points": 50,
        },
    )
    assert resp.status_code == 400
    assert "Insufficient points" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_redemption_rolls_back_with_failed_sale(client):
    """Atomicity: an oversold sale must not spend the customer's points."""
    user, token, client_id = await make_client_account(client)
    pid = await add_product(client_id, user["id"], quantity=100, price=100.0)
    await _seed_program(user["id"], client_id)

    # Build a balance.
    await client.post(
        "/api/v1/pos/transaction",
        headers=auth_headers(token),
        json={
            "items": [{"product_id": pid, "name": "W", "price": 100.0, "quantity": 1}],
            "payment_method": "cash",
            "customer_id": 9,
        },
    )
    before = await _balance(client, token, 9)
    assert before == 115

    # Oversell (request 9999 of a 99-stock product) while redeeming points.
    resp = await client.post(
        "/api/v1/pos/transaction",
        headers=auth_headers(token),
        json={
            "items": [{"product_id": pid, "name": "W", "price": 100.0, "quantity": 9999}],
            "payment_method": "cash",
            "customer_id": 9,
            "redeem_points": 50,
        },
    )
    assert resp.status_code == 400  # insufficient stock
    # Points must be untouched because the whole transaction rolled back.
    assert await _balance(client, token, 9) == before
