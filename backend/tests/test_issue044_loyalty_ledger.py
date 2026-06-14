"""ISSUE-044 — loyalty points ledger + expiry.

Builds on the ISSUE-028 admin endpoints: every earn/redeem/adjust must now write
a dated ``loyalty_transactions`` ledger entry, and the usable balance ages out
credits older than a configurable expiry window.
"""
from datetime import datetime, timedelta

import pytest

from conftest import auth_headers, make_client_account
from core.database import db_manager
from models.customers import Customers
from services.loyalty_points import compute_usable_balance


async def _add_customer(user_id: str, name: str = "Acme Co") -> int:
    async with db_manager.async_session_maker() as db:
        cust = Customers(user_id=user_id, name=name)
        db.add(cust)
        await db.commit()
        await db.refresh(cust)
        return cust.id


@pytest.mark.asyncio
async def test_earn_writes_ledger_entry(client):
    """POST /loyalty/earn records an 'earned' ledger entry [AC1]."""
    user, token, client_id = await make_client_account(client)
    cust_id = await _add_customer(user["id"], name="Earner")

    earn = await client.post(
        "/api/v1/production/loyalty/earn",
        headers=auth_headers(token),
        json={"customer_id": cust_id, "transaction_amount": 50.0, "points_rate": 2.0},
    )
    assert earn.status_code == 200, earn.text

    tx = await client.get(
        "/api/v1/production/loyalty/transactions",
        headers=auth_headers(token),
    )
    assert tx.status_code == 200, tx.text
    body = tx.json()
    assert body["total"] == 1
    entry = body["items"][0]
    assert entry["type"] == "earned"
    assert entry["points"] == 100  # 50 SAR * 2 points/SAR
    assert entry["customer_name"] == "Earner"


@pytest.mark.asyncio
async def test_redeem_writes_ledger_entry(client):
    """POST /loyalty/redeem records a 'redeemed' ledger entry [AC1]."""
    user, token, client_id = await make_client_account(client)
    cust_id = await _add_customer(user["id"], name="Redeemer")

    await client.post(
        "/api/v1/production/loyalty/earn",
        headers=auth_headers(token),
        json={"customer_id": cust_id, "transaction_amount": 100.0, "points_rate": 1.0},
    )
    redeem = await client.post(
        "/api/v1/production/loyalty/redeem",
        headers=auth_headers(token),
        json={"customer_id": cust_id, "points_to_redeem": 40},
    )
    assert redeem.status_code == 200, redeem.text

    tx = await client.get(
        "/api/v1/production/loyalty/transactions",
        headers=auth_headers(token),
    )
    body = tx.json()
    # Newest first: the redeem leg, then the earn leg.
    assert body["total"] == 2
    redeemed = body["items"][0]
    assert redeemed["type"] == "redeemed"
    assert redeemed["points"] == 40


def _entry(type_, points, created_at):
    return {"type": type_, "points": points, "created_at": created_at}


def test_compute_balance_sums_credits_minus_debits_when_no_expiry():
    """With no expiry policy the usable balance is just credits minus debits [AC1]."""
    now = datetime(2026, 6, 14, 12, 0, 0)
    entries = [
        _entry("earned", 100, now - timedelta(days=10)),
        _entry("redeemed", 30, now - timedelta(days=5)),
        _entry("add", 20, now - timedelta(days=1)),
    ]
    assert compute_usable_balance(entries, expiry_days=0, now=now) == 90


def test_compute_balance_drops_credits_older_than_expiry_window():
    """A credit earned before the expiry window no longer counts [AC2]."""
    now = datetime(2026, 6, 14, 12, 0, 0)
    entries = [
        _entry("earned", 100, now - timedelta(days=40)),  # expired (>30d)
        _entry("earned", 50, now - timedelta(days=10)),   # fresh
    ]
    assert compute_usable_balance(entries, expiry_days=30, now=now) == 50


def test_compute_balance_redeems_oldest_credits_first():
    """Redemptions consume the oldest lot first, so it can't 'save' fresh points
    from a redemption while the old lot expires (FIFO) [AC2]."""
    now = datetime(2026, 6, 14, 12, 0, 0)
    entries = [
        _entry("earned", 100, now - timedelta(days=40)),  # old lot
        _entry("earned", 100, now - timedelta(days=10)),  # fresh lot
        _entry("redeemed", 100, now - timedelta(days=1)),  # consumes the old lot
    ]
    # Old lot fully redeemed; fresh lot of 100 remains and is within the window.
    assert compute_usable_balance(entries, expiry_days=30, now=now) == 100


@pytest.mark.asyncio
async def test_config_persists_expiry_policy(client):
    """POST /loyalty/config stores points_expiry_days; GET reloads it [AC2]."""
    user, token, client_id = await make_client_account(client)

    save = await client.post(
        "/api/v1/production/loyalty/config",
        headers=auth_headers(token),
        json={
            "points_per_sar": 1.0,
            "redemption_rate": 0.1,
            "min_points_redeem": 100,
            "points_expiry_days": 90,
            "is_active": True,
        },
    )
    assert save.status_code == 200, save.text
    assert save.json()["points_expiry_days"] == 90

    reload = await client.get(
        "/api/v1/production/loyalty/config",
        headers=auth_headers(token),
    )
    assert reload.json()["points_expiry_days"] == 90


async def _backdate_ledger(user_id: str, days: int) -> None:
    """Push every ledger row for a merchant back in time, simulating aging."""
    from sqlalchemy import update

    from models.loyalty_transactions import Loyalty_transactions

    async with db_manager.async_session_maker() as db:
        await db.execute(
            update(Loyalty_transactions)
            .where(Loyalty_transactions.user_id == user_id)
            .values(created_at=datetime.now() - timedelta(days=days))
        )
        await db.commit()


@pytest.mark.asyncio
async def test_balances_available_points_drop_after_expiry(client):
    """Earn → age past the window → /loyalty/balances available_points falls [AC2/AC4]."""
    user, token, client_id = await make_client_account(client)
    cust_id = await _add_customer(user["id"], name="Ager")

    # 30-day expiry policy.
    await client.post(
        "/api/v1/production/loyalty/config",
        headers=auth_headers(token),
        json={
            "points_per_sar": 1.0,
            "redemption_rate": 0.1,
            "min_points_redeem": 100,
            "points_expiry_days": 30,
            "is_active": True,
        },
    )
    await client.post(
        "/api/v1/production/loyalty/earn",
        headers=auth_headers(token),
        json={"customer_id": cust_id, "transaction_amount": 100.0, "points_rate": 1.0},
    )

    # Before aging: all 100 points are usable.
    fresh = await client.get("/api/v1/production/loyalty/balances", headers=auth_headers(token))
    assert fresh.json()["items"][0]["available_points"] == 100

    # Age the earn beyond the 30-day window.
    await _backdate_ledger(user["id"], days=45)

    aged = await client.get("/api/v1/production/loyalty/balances", headers=auth_headers(token))
    row = aged.json()["items"][0]
    assert row["available_points"] == 0  # expired
    assert row["points_balance"] == 100  # lifetime balance unchanged
