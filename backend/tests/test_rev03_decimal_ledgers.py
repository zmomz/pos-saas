"""REV-03 — secondary ledgers store money as Decimal/Numeric, not Float.

FIN-01/02 made money *computation* exact Decimal and converted the billing
columns, but several non-authoritative ledgers still stored money as ``Float``:
the POS ``transactions`` money columns, the ``gift_card_ledger`` audit rows, and
the offline-replay sale path recomputed subtotal/VAT/total in IEEE-754 float.

These tests pin that those storage types and that replay path are penny-exact:
the stored values round-trip as 2dp ``Decimal`` (the shared ``Money`` column
type), and the offline replay routes its arithmetic through ``core.money`` so a
.xx5 VAT boundary rounds half-up the same way the online path does — not the
float ``round()`` that silently drops a penny.
"""
from decimal import Decimal

import pytest
from sqlalchemy import select

from conftest import auth_headers, make_client_account
from core.database import db_manager
from models.transactions import Transactions


@pytest.mark.asyncio
async def test_offline_replay_vat_and_total_are_penny_exact(client):
    """An offline-replayed sale computes VAT/total via Decimal half-up.

    A 0.10 SAR line at 15% VAT lands VAT exactly on the .005 half-up boundary:
    Decimal half-up gives 0.02 (total 0.12), but float ``round(0.015, 2)`` gives
    0.01 (total 0.11) because 0.015 is 0.014999… in binary. The replay path must
    match the online Decimal path, not the float ``round``.
    """
    user, token, client_id = await make_client_account(client)

    queued = {
        "transactions": [
            {
                "offline_id": "REV03-PENNY-1",
                "client_id": client_id,
                "payment_method": "cash",
                "items": [
                    {"product_id": 1, "name": "Halala item", "price": 0.10, "quantity": 1}
                ],
            }
        ]
    }

    resp = await client.post(
        "/api/v1/production/offline/sync", headers=auth_headers(token), json=queued
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["processed"] == 1

    async with db_manager.async_session_maker() as db:
        txn = (
            await db.execute(
                select(Transactions).where(
                    Transactions.client_id == client_id,
                    Transactions.offline_id == "REV03-PENNY-1",
                )
            )
        ).scalar_one()

    assert txn.subtotal == Decimal("0.10")
    assert txn.vat_amount == Decimal("0.02")
    assert txn.total_amount == Decimal("0.12")


@pytest.mark.asyncio
async def test_transaction_money_columns_round_trip_penny_exact():
    """The POS transaction money columns store and return 2dp Decimals.

    A value that drifts under a REAL/float affinity must read back in a fresh
    session as a Decimal equal to the quantized input — not 19.989999….
    """
    async with db_manager.async_session_maker() as db:
        row = Transactions(
            user_id="rev03-user",
            client_id=999001,
            invoice_number="INV-REV03-COL-1",
            subtotal=Decimal("19.99"),
            vat_amount=Decimal("3.00"),
            discount_amount=Decimal("0.10"),
            total_amount=Decimal("22.89"),
            tip_amount=Decimal("1.05"),
            cash_tendered=Decimal("25.00"),
            change_due=Decimal("1.06"),
            payment_method="cash",
            status="completed",
        )
        db.add(row)
        await db.commit()
        row_id = row.id

    async with db_manager.async_session_maker() as db:
        stored = (
            await db.execute(select(Transactions).where(Transactions.id == row_id))
        ).scalar_one()

    for col, expected in (
        ("subtotal", "19.99"),
        ("vat_amount", "3.00"),
        ("discount_amount", "0.10"),
        ("total_amount", "22.89"),
        ("tip_amount", "1.05"),
        ("cash_tendered", "25.00"),
        ("change_due", "1.06"),
    ):
        value = getattr(stored, col)
        assert isinstance(value, Decimal), f"{col} came back as {type(value)}"
        assert value == Decimal(expected), f"{col} == {value}"


@pytest.mark.asyncio
async def test_gift_card_ledger_money_columns_round_trip_penny_exact():
    """``gift_card_ledger`` amount/balance_after store and return 2dp Decimals."""
    from models.gift_card_ledger import GiftCardLedger

    async with db_manager.async_session_maker() as db:
        row = GiftCardLedger(
            user_id="rev03-user",
            client_id=999001,
            gift_card_id=1,
            entry_type="reload",
            amount=Decimal("0.30") - Decimal("0.10"),
            balance_after=Decimal("19.99"),
        )
        db.add(row)
        await db.commit()
        row_id = row.id

    async with db_manager.async_session_maker() as db:
        stored = (
            await db.execute(
                select(GiftCardLedger).where(GiftCardLedger.id == row_id)
            )
        ).scalar_one()

    assert isinstance(stored.amount, Decimal)
    assert stored.amount == Decimal("0.20")
    assert isinstance(stored.balance_after, Decimal)
    assert stored.balance_after == Decimal("19.99")
