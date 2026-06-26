"""Phase 6 — accounting journal / general-ledger export (F-043 / FIN-02, P1).

FIN-02 is the accountant hand-off: *"standard journal / general-ledger CSV
(sales, VAT, COGS, payments)."* The export is a balanced double-entry journal
for the period — the cash/bank legs (by real captured tender), sales revenue,
output VAT, and COGS vs inventory. These tests prove:

* the journal **balances** (``Σ debit == Σ credit``) — the defining property of
  a double-entry journal — across sales, split tenders, and a refund credit note;
* revenue / VAT / COGS / payments-by-tender all surface on their GL accounts;
* the export stays client-scoped (an agent is 403; one client never sees
  another's books).
"""
import itertools
import json
from datetime import datetime, timezone, timedelta

from conftest import auth_headers, make_client_account, make_agent_account
from core.database import db_manager
from models.products import Products
from models.transactions import Transactions
from models.payment_tenders import PaymentTenders


async def _add_product_with_cost(client_id: int, user_id: str, name: str, cost: float) -> int:
    async with db_manager.async_session_maker() as db:
        product = Products(
            user_id=user_id,
            client_id=client_id,
            name=name,
            price=cost * 2,
            cost_price=cost,
            quantity=100,
            is_active=True,
        )
        db.add(product)
        await db.commit()
        await db.refresh(product)
        return product.id


_txn_seq = itertools.count(1)


async def _add_txn(client_id, user_id, *, items, subtotal, vat, total, status, days_ago=1):
    created = datetime.now(timezone.utc) - timedelta(days=days_ago, hours=1)
    async with db_manager.async_session_maker() as db:
        txn = Transactions(
            user_id=user_id,
            client_id=client_id,
            # Unique per row: real sales mint distinct fiscal numbers (DAT-05), so
            # the synthetic number must not collide when two sales share a total.
            invoice_number=f"INV-{client_id:04d}-{next(_txn_seq):06d}",
            subtotal=subtotal,
            vat_amount=vat,
            discount_amount=0.0,
            total_amount=total,
            payment_method="cash",
            status=status,
            items_json=json.dumps(items, ensure_ascii=False),
            created_at=created,
        )
        db.add(txn)
        await db.commit()
        await db.refresh(txn)
        return txn.id


async def _add_tender(client_id, user_id, txn_id, tender_type, amount, status, days_ago=1):
    created = datetime.now(timezone.utc) - timedelta(days=days_ago, hours=1)
    async with db_manager.async_session_maker() as db:
        db.add(
            PaymentTenders(
                user_id=user_id,
                client_id=client_id,
                transaction_id=txn_id,
                tender_type=tender_type,
                amount=amount,
                status=status,
                gateway="sandbox",
                created_at=created,
            )
        )
        await db.commit()


async def test_journal_export_balances_across_sales_and_a_refund(client):
    """FIN-02: the double-entry journal balances and books each GL account.

    Two sales (cash + Mada) and a partial Mada refund. The revenue, VAT, COGS,
    inventory and cash/bank legs must reconcile so Σ debit == Σ credit.
    """
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    a = await _add_product_with_cost(client_id, user["id"], "Widget A", cost=4.0)
    b = await _add_product_with_cost(client_id, user["id"], "Widget B", cost=2.5)

    # Sale 1 — cash: 2 x A @ 10 = 20 + 15% VAT (3) = 23.
    s1 = await _add_txn(
        client_id, user["id"],
        items=[{"product_id": a, "quantity": 2, "price": 10}],
        subtotal=20.0, vat=3.0, total=23.0, status="completed",
    )
    await _add_tender(client_id, user["id"], s1, "cash", 23.0, "captured")

    # Sale 2 — Mada: 4 x B @ 5 = 20 + 3 VAT = 23.
    s2 = await _add_txn(
        client_id, user["id"],
        items=[{"product_id": b, "quantity": 4, "price": 5}],
        subtotal=20.0, vat=3.0, total=23.0, status="completed",
    )
    await _add_tender(client_id, user["id"], s2, "mada", 23.0, "captured")

    # Refund 1 unit of B → credit note (negative amounts), reversed to Mada.
    cn = await _add_txn(
        client_id, user["id"],
        items=[{"product_id": b, "quantity": 1, "price": 5}],
        subtotal=-5.0, vat=-0.75, total=-5.75, status="credit_note",
    )
    await _add_tender(client_id, user["id"], cn, "mada", 5.75, "refunded")

    resp = await client.get("/api/v1/reports/journal-export?days=30", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # The defining property: a double-entry journal balances.
    assert body["balanced"] is True
    assert body["total_debit"] == body["total_credit"]
    # gross 40.25 + COGS 15.5 on each side.
    assert body["total_debit"] == 55.75

    by_account = {line["account"]: line for line in body["lines"]}

    # Revenue = total(40.25) − VAT(5.25) = 35.00 (credited).
    assert by_account["Sales Revenue"]["credit"] == 35.0
    assert by_account["Sales Revenue"]["debit"] == 0.0
    # Output VAT = 3 + 3 − 0.75 = 5.25 (credited).
    assert by_account["VAT Payable"]["credit"] == 5.25
    # COGS = 2*4 + 4*2.5 − 1*2.5 = 15.5 (debited); inventory credited the same.
    assert by_account["Cost of Goods Sold"]["debit"] == 15.5
    assert by_account["Inventory"]["credit"] == 15.5

    # Cash leg = 23 (Dr); card/wallet clearing nets the Mada refund: 23 − 5.75 = 17.25.
    assert by_account["Cash on Hand"]["debit"] == 23.0
    assert by_account["Card/Wallet Clearing"]["debit"] == 17.25

    # The CSV carries a balancing TOTAL row.
    assert "Cost of Goods Sold" in body["csv_content"]
    assert body["csv_content"].strip().endswith("55.75,55.75")


async def test_journal_export_balances_with_no_tender_rows(client):
    """A legacy cash-only sale with no payment_tenders still balances.

    The untendered remainder is booked to Cash on Hand so the cash side
    reconciles to revenue + VAT exactly.
    """
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    a = await _add_product_with_cost(client_id, user["id"], "Widget", cost=3.0)
    await _add_txn(
        client_id, user["id"],
        items=[{"product_id": a, "quantity": 1, "price": 10}],
        subtotal=10.0, vat=1.5, total=11.5, status="completed",
    )
    # No payment_tenders row at all.

    resp = await client.get("/api/v1/reports/journal-export?days=30", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["balanced"] is True
    assert body["total_debit"] == body["total_credit"]

    by_account = {line["account"]: line for line in body["lines"]}
    # The whole 11.5 lands as the untendered cash remainder.
    assert by_account["Cash on Hand"]["debit"] == 11.5
    assert by_account["Sales Revenue"]["credit"] == 10.0
    assert by_account["VAT Payable"]["credit"] == 1.5


async def test_journal_export_is_client_scoped(client):
    """SEC-02: an agent is 403; one client never sees another client's books."""
    user_a, token_a, client_a = await make_client_account(client)
    user_b, token_b, client_b = await make_client_account(client)

    a = await _add_product_with_cost(client_a, user_a["id"], "A", cost=1.0)
    b = await _add_product_with_cost(client_b, user_b["id"], "B", cost=1.0)
    sa = await _add_txn(client_a, user_a["id"], items=[{"product_id": a, "quantity": 1, "price": 10}],
                        subtotal=10.0, vat=1.5, total=11.5, status="completed")
    await _add_tender(client_a, user_a["id"], sa, "cash", 11.5, "captured")
    sb = await _add_txn(client_b, user_b["id"], items=[{"product_id": b, "quantity": 1, "price": 100}],
                        subtotal=100.0, vat=15.0, total=115.0, status="completed")
    await _add_tender(client_b, user_b["id"], sb, "cash", 115.0, "captured")

    # Client A's journal totals only A's 11.5 — never B's 115.
    resp_a = await client.get("/api/v1/reports/journal-export?days=30", headers=auth_headers(token_a))
    assert resp_a.status_code == 200, resp_a.text
    body_a = resp_a.json()
    assert body_a["balanced"] is True
    # gross 11.5 + COGS (1 unit * cost 1.0 = 1.0) on each side → 12.5.
    assert body_a["total_debit"] == 12.5

    # An agent cannot read merchant books.
    _, agent_token, _ = await make_agent_account(client)
    resp_agent = await client.get(
        "/api/v1/reports/journal-export", headers=auth_headers(agent_token)
    )
    assert resp_agent.status_code == 403, resp_agent.text
