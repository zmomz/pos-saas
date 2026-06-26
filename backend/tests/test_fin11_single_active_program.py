"""FIN-11 — enforce a single authoritative active loyalty program per tenant.

Two writers (the generic ``/entities/loyalty_programs`` CRUD and the
``/production/loyalty/config`` single-upsert) plus ``get_active_program``
picking the highest id made the POS non-deterministic: a stray second active
program could silently shadow the configured one. These cover the invariant —
at most one active program per tenant — across both writers, and that the POS
deterministically uses it.
"""
import pytest
from sqlalchemy import func, select

from conftest import add_product, auth_headers, make_client_account
from core.database import db_manager
from models.loyalty_programs import Loyalty_programs


async def _active_count(user_id: str) -> int:
    async with db_manager.async_session_maker() as db:
        result = await db.execute(
            select(func.count(Loyalty_programs.id)).where(
                Loyalty_programs.user_id == user_id,
                Loyalty_programs.is_active == True,  # noqa: E712
            )
        )
        return result.scalar()


def _create_program(client, token, **fields):
    payload = {"name": "Rewards", "is_active": True}
    payload.update(fields)
    return client.post(
        "/api/v1/entities/loyalty_programs",
        headers=auth_headers(token),
        json=payload,
    )


@pytest.mark.asyncio
async def test_generic_crud_second_active_deactivates_first(client):
    """Creating a second active program via the CRUD endpoint deactivates the
    first — exactly one active program remains for the tenant."""
    user, token, client_id = await make_client_account(client)

    first = await _create_program(client, token, name="Old", points_per_sar=1.0)
    assert first.status_code == 201, first.text
    second = await _create_program(client, token, name="New", points_per_sar=2.0)
    assert second.status_code == 201, second.text

    assert await _active_count(user["id"]) == 1


@pytest.mark.asyncio
async def test_config_save_keeps_single_active_under_stray(client):
    """Saving the config deactivates a stray active program and round-trips:
    exactly one active program, and GET reflects the saved values."""
    user, token, client_id = await make_client_account(client)

    # A stray active program with different values sneaks in via the CRUD writer.
    stray = await _create_program(client, token, name="Stray", points_per_sar=99.0)
    assert stray.status_code == 201, stray.text

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

    assert await _active_count(user["id"]) == 1

    reload = await client.get(
        "/api/v1/production/loyalty/config",
        headers=auth_headers(token),
    )
    assert reload.status_code == 200, reload.text
    assert reload.json()["points_per_sar"] == 2.0
    assert reload.json()["is_active"] is True


@pytest.mark.asyncio
async def test_config_targets_authoritative_active_program(client):
    """Config GET/POST resolve to the *active* program even when a more recent
    inactive program exists — so the config page and the POS agree."""
    user, token, client_id = await make_client_account(client)

    # The configured, active program.
    save = await client.post(
        "/api/v1/production/loyalty/config",
        headers=auth_headers(token),
        json={"points_per_sar": 2.0, "redemption_rate": 0.25,
              "min_points_redeem": 50, "is_active": True},
    )
    assert save.status_code == 200, save.text

    # A newer *inactive* program is added via the CRUD writer.
    newer = await _create_program(
        client, token, name="Draft", points_per_sar=99.0, is_active=False
    )
    assert newer.status_code == 201, newer.text

    reload = await client.get(
        "/api/v1/production/loyalty/config",
        headers=auth_headers(token),
    )
    assert reload.status_code == 200, reload.text
    # The active program (pps=2.0), not the newer inactive draft (pps=99.0).
    assert reload.json()["points_per_sar"] == 2.0
    assert reload.json()["is_active"] is True
    assert await _active_count(user["id"]) == 1


@pytest.mark.asyncio
async def test_pos_accrues_against_the_single_surviving_program(client):
    """With two programs created active, only the last survives active and the
    POS deterministically accrues at *its* rate."""
    user, token, client_id = await make_client_account(client)
    pid = await add_product(client_id, user["id"], quantity=100, price=100.0)

    # First active program at 1 pt/SAR, then a second at 3 pt/SAR which
    # supersedes it (single-active invariant).
    first = await _create_program(client, token, name="One", points_per_sar=1.0)
    assert first.status_code == 201, first.text
    second = await _create_program(client, token, name="Three", points_per_sar=3.0)
    assert second.status_code == 201, second.text
    assert await _active_count(user["id"]) == 1

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
    # subtotal 100 + 15% VAT = 115 total; surviving program earns 3 pt/SAR => 345.
    assert resp.json()["total_amount"] == 115.0
    assert resp.json()["loyalty_points_earned"] == 345
