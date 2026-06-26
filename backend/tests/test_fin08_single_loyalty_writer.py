"""FIN-08 — a single authoritative writer for every loyalty-point movement.

The POS sale path (``services/loyalty.py``) used to mutate ``loyalty_points``
balances without writing the ``loyalty_transactions`` ledger that the admin UI
and the expiry engine read, so balances diverged. These tests pin the invariant
that **every** points change leaves exactly one ledger row, and that the generic
CRUD PUT can no longer silently move a balance behind the ledger's back.
"""
import pytest
from sqlalchemy import select

from conftest import add_product, auth_headers, make_client_account
from core.database import db_manager
from models.loyalty_programs import Loyalty_programs
from models.loyalty_points import Loyalty_points
from models.loyalty_transactions import Loyalty_transactions
from services.loyalty_points import compute_usable_balance


async def _seed_program(user_id: str, client_id: int, **kw):
    defaults = dict(
        points_per_sar=1.0,
        redemption_rate=0.5,
        min_redemption_points=10,
        is_active=True,
    )
    defaults.update(kw)
    async with db_manager.async_session_maker() as db:
        db.add(
            Loyalty_programs(
                user_id=user_id, client_id=client_id, name="Rewards", **defaults
            )
        )
        await db.commit()


async def _ledger(user_id: str, customer_id: int):
    async with db_manager.async_session_maker() as db:
        rows = (
            await db.execute(
                select(Loyalty_transactions)
                .where(
                    Loyalty_transactions.user_id == user_id,
                    Loyalty_transactions.customer_id == customer_id,
                )
                .order_by(Loyalty_transactions.id)
            )
        ).scalars().all()
        return [
            {"type": r.type, "points": r.points, "created_at": r.created_at}
            for r in rows
        ]


async def _stored_balance(user_id: str, customer_id: int) -> int:
    async with db_manager.async_session_maker() as db:
        row = (
            await db.execute(
                select(Loyalty_points).where(
                    Loyalty_points.user_id == user_id,
                    Loyalty_points.customer_id == customer_id,
                )
            )
        ).scalar_one_or_none()
        return (row.points_balance or 0) if row else 0


async def _sale(client, token, pid, customer_id, **extra):
    payload = {
        "items": [{"product_id": pid, "name": "Widget", "price": 100.0, "quantity": 1}],
        "payment_method": "cash",
        "customer_id": customer_id,
    }
    payload.update(extra)
    resp = await client.post(
        "/api/v1/pos/transaction", headers=auth_headers(token), json=payload
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_pos_accrual_writes_one_earned_ledger_row(client):
    """A POS sale that accrues points writes exactly one 'earned' ledger row [AC1]."""
    user, token, client_id = await make_client_account(client)
    pid = await add_product(client_id, user["id"], quantity=100, price=100.0)
    await _seed_program(user["id"], client_id)

    body = await _sale(client, token, pid, customer_id=11)
    assert body["loyalty_points_earned"] == 115  # 100 + 15% VAT, 1 pt/SAR

    ledger = await _ledger(user["id"], 11)
    assert len(ledger) == 1
    assert ledger[0]["type"] == "earned"
    assert ledger[0]["points"] == 115


@pytest.mark.asyncio
async def test_pos_redeem_writes_ledger_and_balance_has_parity(client):
    """A redeeming sale writes one 'redeemed' row, and the ledger-derived balance
    equals the stored balance with one row per movement — no double-write [AC1/AC2]."""
    user, token, client_id = await make_client_account(client)
    pid = await add_product(client_id, user["id"], quantity=100, price=100.0)
    await _seed_program(user["id"], client_id)

    # Sale 1 builds a balance of 115 (one 'earned' row).
    await _sale(client, token, pid, customer_id=22)
    # Sale 2 redeems 100 (0.5 SAR/pt => 50 discount) then accrues floor(57.5)=57.
    body = await _sale(client, token, pid, customer_id=22, redeem_points=100)
    assert body["loyalty_points_redeemed"] == 100
    assert body["loyalty_points_earned"] == 57
    assert body["loyalty_balance"] == 72  # 115 - 100 + 57

    ledger = await _ledger(user["id"], 22)
    # Exactly three movements: earned(115), redeemed(100), earned(57). No double-write.
    assert [(e["type"], e["points"]) for e in ledger] == [
        ("earned", 115),
        ("redeemed", 100),
        ("earned", 57),
    ]
    # Balance parity: the ledger is the source of truth for the stored balance.
    assert compute_usable_balance(ledger, expiry_days=0) == 72
    assert await _stored_balance(user["id"], 22) == 72


async def _seed_balance_row(user_id: str, customer_id: int, balance: int) -> int:
    async with db_manager.async_session_maker() as db:
        row = Loyalty_points(
            user_id=user_id,
            customer_id=customer_id,
            points_balance=balance,
            total_earned=balance,
            total_redeemed=0,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row.id


@pytest.mark.asyncio
async def test_crud_put_cannot_mutate_balance_behind_the_ledger(client):
    """The generic entities PUT is read-only on the balance fields, so it can't
    move a balance without a ledger row — the ledger stays the single source [AC1]."""
    user, token, client_id = await make_client_account(client)
    row_id = await _seed_balance_row(user["id"], customer_id=33, balance=500)

    resp = await client.put(
        f"/api/v1/entities/loyalty_points/{row_id}",
        headers=auth_headers(token),
        json={"points_balance": 999999, "total_redeemed": 7},
    )
    # The request is accepted but the protected balance fields are ignored.
    assert resp.status_code == 200, resp.text

    # Balance untouched and no ledger row was conjured.
    assert await _stored_balance(user["id"], 33) == 500
    assert await _ledger(user["id"], 33) == []
