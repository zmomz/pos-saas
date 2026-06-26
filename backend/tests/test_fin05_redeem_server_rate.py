"""FIN-05 — the standalone /loyalty/redeem endpoint must value redeemed points
from the merchant's server-side rate, never a client-supplied per-point value,
and cap the discount at the order subtotal (mirroring the atomic POS path).
"""
import pytest

from conftest import auth_headers, make_client_account
from core.database import db_manager
from models.customers import Customers


async def _add_customer(user_id: str, name: str = "Redeemer") -> int:
    async with db_manager.async_session_maker() as db:
        cust = Customers(user_id=user_id, name=name)
        db.add(cust)
        await db.commit()
        await db.refresh(cust)
        return cust.id


async def _earn(client, token, cust_id, amount, rate=1.0):
    r = await client.post(
        "/api/v1/production/loyalty/earn",
        headers=auth_headers(token),
        json={"customer_id": cust_id, "transaction_amount": amount, "points_rate": rate},
    )
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_redeem_ignores_client_supplied_value(client):
    """A client-supplied redemption_value is ignored; the discount is computed
    from the platform default rate when no program is configured [AC1]."""
    user, token, _ = await make_client_account(client)
    cust_id = await _add_customer(user["id"])
    await _earn(client, token, cust_id, amount=100.0)  # 100 points

    redeem = await client.post(
        "/api/v1/production/loyalty/redeem",
        headers=auth_headers(token),
        # Attacker tries to value each point at 1000 SAR.
        json={"customer_id": cust_id, "points_to_redeem": 40, "redemption_value": 1000.0},
    )
    assert redeem.status_code == 200, redeem.text
    # 40 points * default 0.1 SAR/point = 4.00, NOT 40 * 1000.
    assert redeem.json()["discount_value"] == 4.0


@pytest.mark.asyncio
async def test_redeem_uses_program_configured_rate(client):
    """When the merchant has an active program, its server-side redemption_rate
    drives the discount value [AC2]."""
    user, token, _ = await make_client_account(client)
    cust_id = await _add_customer(user["id"])
    await _earn(client, token, cust_id, amount=100.0)  # 100 points

    cfg = await client.post(
        "/api/v1/production/loyalty/config",
        headers=auth_headers(token),
        json={
            "points_per_sar": 1.0,
            "redemption_rate": 0.25,
            "min_points_redeem": 0,
            "points_expiry_days": 0,
            "is_active": True,
        },
    )
    assert cfg.status_code == 200, cfg.text

    redeem = await client.post(
        "/api/v1/production/loyalty/redeem",
        headers=auth_headers(token),
        json={"customer_id": cust_id, "points_to_redeem": 40},
    )
    assert redeem.status_code == 200, redeem.text
    # 40 points * 0.25 = 10.00
    assert redeem.json()["discount_value"] == 10.0


@pytest.mark.asyncio
async def test_redeem_caps_discount_at_order_subtotal(client):
    """An optional order_subtotal caps the discount; a redemption worth more than
    the order is rejected, just like the atomic POS path [AC3]."""
    user, token, _ = await make_client_account(client)
    cust_id = await _add_customer(user["id"])
    await _earn(client, token, cust_id, amount=100.0)  # 100 points

    # 40 points * default 0.1 = 4.00 discount, but the order is only 2.00.
    redeem = await client.post(
        "/api/v1/production/loyalty/redeem",
        headers=auth_headers(token),
        json={"customer_id": cust_id, "points_to_redeem": 40, "order_subtotal": 2.0},
    )
    assert redeem.status_code == 400, redeem.text
    # Points were not deducted: balance untouched on rejection.
    bal = await client.get(
        f"/api/v1/production/loyalty/balance?customer_id={cust_id}",
        headers=auth_headers(token),
    )
    assert bal.json()["points_balance"] == 100
