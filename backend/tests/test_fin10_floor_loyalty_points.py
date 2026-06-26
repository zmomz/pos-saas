"""FIN-10 — floor loyalty points without float-truncation drift.

Points earned are ``amount * points_per_sar`` floored to a whole point. Doing the
multiply in IEEE-754 float first lets drift turn an exact ``29.00`` into
``28.999…`` so a plain ``int()`` truncates a point off the customer's balance
(``0.29 * 100`` → float ``28.999999999999996`` → ``int()`` = 28, not 29).

Routing both accrual sites — the POS sale path (``services/loyalty.accrue_points``)
and the standalone ``/loyalty/earn`` endpoint — through an exact-Decimal floor in
``core.money`` keeps the boundary honest while still flooring real fractions down.
"""
import pytest

from conftest import auth_headers, make_client_account
from core.database import db_manager
from core.money import floor_units
from models.customers import Customers
from models.loyalty_programs import Loyalty_programs
from services.loyalty import accrue_points


def test_floor_units_keeps_exact_boundary_no_float_truncation():
    """0.29 * 100 is exactly 29 — float drift must not truncate it to 28 [AC1]."""
    assert int(0.29 * 100) == 28  # the float trap this helper exists to avoid
    assert floor_units(0.29, 100) == 29


def test_floor_units_floors_real_fractions_down():
    """A genuine fraction still floors toward zero (4.35 * 10 = 43.5 → 43) [AC1]."""
    assert floor_units(4.35, 10) == 43
    assert floor_units(2.5, 1) == 2
    assert floor_units(0.9, 1) == 0


@pytest.mark.asyncio
async def test_accrue_points_awards_exact_boundary(client):
    """POS accrual at a drift boundary awards the full point, not one less [AC1]."""
    user, _token, client_id = await make_client_account(client)
    program = Loyalty_programs(
        user_id=user["id"], client_id=client_id, name="Rewards",
        points_per_sar=100.0, redemption_rate=0.5, min_redemption_points=10,
        is_active=True,
    )
    async with db_manager.async_session_maker() as db:
        db.add(program)
        await db.commit()
        await db.refresh(program)

        result = await accrue_points(
            db, user_id=user["id"], client_id=client_id, customer_id=7,
            total_amount=0.29, program=program,
        )
        await db.commit()

    assert result is not None
    assert result.points_earned == 29


@pytest.mark.asyncio
async def test_earn_endpoint_awards_exact_boundary(client):
    """POST /loyalty/earn at a drift boundary awards the full point [AC1]."""
    user, token, client_id = await make_client_account(client)
    async with db_manager.async_session_maker() as db:
        cust = Customers(user_id=user["id"], name="Acme Co")
        db.add(cust)
        await db.commit()
        await db.refresh(cust)
        cust_id = cust.id

    resp = await client.post(
        "/api/v1/production/loyalty/earn",
        headers=auth_headers(token),
        json={"customer_id": cust_id, "transaction_amount": 0.29, "points_rate": 100.0},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["points_earned"] == 29
