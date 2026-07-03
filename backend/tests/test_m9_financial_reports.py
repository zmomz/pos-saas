"""M9 — financial-reporting service: P&L, COGS (BOM roll-up), cash flow.

These prove the new financial statements added under #205:

* the **P&L** nets revenue (ex-VAT) − COGS − operating expenses to a net profit,
  tenant-scoped and SQL-aggregated;
* **COGS rolls up from the bill of materials** when a sold parent carries no
  sale-time cost snapshot and no own cost — its components' costs become the COGS;
* the **cash flow** statement reports receipts (net of refunds), operating
  expenses, and drawer movements, with a correct operating-cash-flow net;
* both reports are owner-scoped (a second tenant's data never leaks in).
"""
import json
from datetime import datetime, timezone, timedelta

from conftest import auth_headers, make_client_account
from core.database import db_manager
from models.transactions import Transactions
from models.expenses import Expenses
from models.products import Products
from models.restaurant import BillOfMaterials
from models.payment_tenders import PaymentTenders
from models.cash_movements import Cash_movements


async def _seed_sale(
    client_id, user_id, *, subtotal, vat, discount, items, status="completed",
    days_ago=1, invoice="INV", payment_method="cash",
):
    total = subtotal + vat - discount
    created = datetime.now(timezone.utc) - timedelta(days=days_ago, hours=1)
    async with db_manager.async_session_maker() as db:
        db.add(
            Transactions(
                user_id=user_id,
                client_id=client_id,
                invoice_number=invoice,
                subtotal=subtotal,
                vat_amount=vat,
                discount_amount=discount,
                total_amount=total,
                payment_method=payment_method,
                status=status,
                items_json=json.dumps(items) if items is not None else None,
                created_at=created,
            )
        )
        await db.commit()


async def _add(obj):
    async with db_manager.async_session_maker() as db:
        db.add(obj)
        await db.commit()


async def test_pnl_nets_revenue_cogs_expenses(client):
    """P&L: net revenue − COGS − operating expenses = net profit (tenant-scoped)."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    # One sale: subtotal 100, VAT 15, discount 10 → net revenue 90.
    # Line carries a sale-time cost snapshot of 40 → COGS 40.
    await _seed_sale(
        client_id, user["id"], subtotal=100.0, vat=15.0, discount=10.0,
        items=[{"product_id": 1, "name": "Widget", "price": 100.0, "quantity": 1, "cost_price": 40.0}],
        invoice="INV-1",
    )
    # Operating expenses: 30 rent + 5 supplies. Stamp an explicit UTC created_at
    # (like the sale above) so the report's UTC window matches regardless of the
    # test runner's local timezone — the model default is naive local time.
    expensed_at = datetime.now(timezone.utc) - timedelta(hours=1)
    await _add(Expenses(user_id=user["id"], client_id=client_id, category="Rent", amount=30.0, created_at=expensed_at))
    await _add(Expenses(user_id=user["id"], client_id=client_id, category="Supplies", amount=5.0, created_at=expensed_at))

    resp = await client.get("/api/v1/reports/pnl?days=30", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert abs(body["gross_sales"] - 100.0) < 0.01
    assert abs(body["discounts"] - 10.0) < 0.01
    assert abs(body["net_revenue"] - 90.0) < 0.01
    assert abs(body["vat"] - 15.0) < 0.01      # VAT is excluded from revenue
    assert abs(body["cogs"] - 40.0) < 0.01
    assert abs(body["gross_profit"] - 50.0) < 0.01   # 90 − 40
    assert abs(body["total_expenses"] - 35.0) < 0.01
    assert abs(body["net_profit"] - 15.0) < 0.01     # 50 − 35
    # Margins are relative to net revenue.
    assert abs(body["gross_margin_pct"] - round(50.0 / 90.0 * 100, 2)) < 0.01
    cats = {e["category"]: e["amount"] for e in body["expenses"]}
    assert cats == {"Rent": 30.0, "Supplies": 5.0}
    assert body["csv_content"]


async def test_pnl_credit_note_reverses_revenue_and_cogs(client):
    """A credit note nets both revenue and COGS down (signed sums)."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    await _seed_sale(
        client_id, user["id"], subtotal=100.0, vat=15.0, discount=0.0,
        items=[{"product_id": 1, "name": "W", "price": 100.0, "quantity": 1, "cost_price": 40.0}],
        invoice="INV-2",
    )
    # Refund of half (credit note carries negative signed amounts).
    await _seed_sale(
        client_id, user["id"], subtotal=-50.0, vat=-7.5, discount=0.0,
        items=[{"product_id": 1, "name": "W", "price": -50.0, "quantity": 1, "cost_price": 20.0}],
        status="credit_note", invoice="INV-2-CN",
    )

    body = (await client.get("/api/v1/reports/pnl?days=30", headers=headers)).json()
    # Revenue 100 − 50 = 50; COGS 40 − 20 = 20; gross 30.
    assert abs(body["net_revenue"] - 50.0) < 0.01
    assert abs(body["cogs"] - 20.0) < 0.01
    assert abs(body["gross_profit"] - 30.0) < 0.01


async def test_cogs_rolls_up_from_bom(client):
    """COGS uses the BOM roll-up when a sold parent has no snapshot and no own cost."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    # Parent burger (cost_price 0) made of 1× patty (cost 8) + 2× bun (cost 1).
    async with db_manager.async_session_maker() as db:
        burger = Products(user_id=user["id"], client_id=client_id, name="Burger", price=25.0, cost_price=0.0)
        patty = Products(user_id=user["id"], client_id=client_id, name="Patty", price=0.0, cost_price=8.0)
        bun = Products(user_id=user["id"], client_id=client_id, name="Bun", price=0.0, cost_price=1.0)
        db.add_all([burger, patty, bun])
        await db.commit()
        await db.refresh(burger); await db.refresh(patty); await db.refresh(bun)
        db.add_all([
            BillOfMaterials(user_id=user["id"], client_id=client_id,
                            parent_product_id=burger.id, component_product_id=patty.id, qty_per=1.0),
            BillOfMaterials(user_id=user["id"], client_id=client_id,
                            parent_product_id=burger.id, component_product_id=bun.id, qty_per=2.0),
        ])
        await db.commit()
        burger_id = burger.id

    # Sell 2 burgers, NO cost snapshot on the line (legacy/restaurant fired line).
    await _seed_sale(
        client_id, user["id"], subtotal=50.0, vat=7.5, discount=0.0,
        items=[{"product_id": burger_id, "name": "Burger", "price": 25.0, "quantity": 2}],
        invoice="INV-BOM",
    )

    body = (await client.get("/api/v1/reports/pnl?days=30", headers=headers)).json()
    # Effective parent cost = 8 + 2×1 = 10; ×2 sold = 20 COGS.
    assert abs(body["cogs"] - 20.0) < 0.01
    assert abs(body["gross_profit"] - 30.0) < 0.01   # net revenue 50 − 20


async def test_cash_flow_receipts_minus_expenses(client):
    """Cash flow: receipts (net of refunds) − operating expenses, plus drawer."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    now = datetime.now(timezone.utc) - timedelta(days=1)
    async with db_manager.async_session_maker() as db:
        db.add_all([
            PaymentTenders(user_id=user["id"], client_id=client_id, tender_type="cash",
                           amount=200.0, status="captured", created_at=now),
            PaymentTenders(user_id=user["id"], client_id=client_id, tender_type="card",
                           amount=100.0, status="captured", created_at=now),
            PaymentTenders(user_id=user["id"], client_id=client_id, tender_type="cash",
                           amount=50.0, status="refunded", created_at=now),
            # A declined leg must be ignored entirely.
            PaymentTenders(user_id=user["id"], client_id=client_id, tender_type="card",
                           amount=999.0, status="declined", created_at=now),
        ])
        db.add(Expenses(user_id=user["id"], client_id=client_id, category="Rent", amount=80.0, created_at=now))
        db.add_all([
            Cash_movements(user_id=user["id"], client_id=client_id, shift_id=1,
                           movement_type="pay_in", amount=20.0, created_at=now),
            Cash_movements(user_id=user["id"], client_id=client_id, shift_id=1,
                           movement_type="pay_out", amount=15.0, created_at=now),
            Cash_movements(user_id=user["id"], client_id=client_id, shift_id=1,
                           movement_type="cash_drop", amount=100.0, created_at=now),
        ])
        await db.commit()

    body = (await client.get("/api/v1/reports/cash-flow?days=30", headers=headers)).json()
    # Receipts collected 300, refunds 50, net 250.
    assert abs(body["receipts_collected"] - 300.0) < 0.01
    assert abs(body["receipts_refunds"] - 50.0) < 0.01
    assert abs(body["receipts_net"] - 250.0) < 0.01
    assert abs(body["total_expenses"] - 80.0) < 0.01
    # Net operating cash flow = 250 − 80 = 170.
    assert abs(body["net_cash_flow"] - 170.0) < 0.01
    dm = body["drawer_movements"]
    assert abs(dm["pay_in"] - 20.0) < 0.01
    assert abs(dm["pay_out"] - 15.0) < 0.01
    assert abs(dm["cash_drop"] - 100.0) < 0.01
    assert abs(dm["net_drawer"] - (-95.0)) < 0.01   # 20 − 15 − 100
    # Tender split present and the declined leg dropped.
    tenders = {t["tender_type"]: t for t in body["by_tender"]}
    assert abs(tenders["cash"]["net"] - 150.0) < 0.01   # 200 − 50
    assert abs(tenders["card"]["net"] - 100.0) < 0.01
    assert body["csv_content"]


async def test_financial_reports_are_tenant_scoped(client):
    """A second tenant's sales/expenses never leak into the first's P&L."""
    user_a, token_a, cid_a = await make_client_account(client)
    user_b, token_b, cid_b = await make_client_account(client)

    await _seed_sale(cid_a, user_a["id"], subtotal=100.0, vat=15.0, discount=0.0,
                     items=[{"product_id": 1, "name": "A", "price": 100.0, "quantity": 1, "cost_price": 40.0}],
                     invoice="A-1")
    await _seed_sale(cid_b, user_b["id"], subtotal=999.0, vat=0.0, discount=0.0,
                     items=[{"product_id": 9, "name": "B", "price": 999.0, "quantity": 1, "cost_price": 1.0}],
                     invoice="B-1")
    await _add(Expenses(user_id=user_b["id"], client_id=cid_b, category="Rent", amount=500.0))

    body = (await client.get("/api/v1/reports/pnl?days=30", headers=auth_headers(token_a))).json()
    assert abs(body["net_revenue"] - 100.0) < 0.01   # only tenant A's sale
    assert abs(body["cogs"] - 40.0) < 0.01
    assert body["total_expenses"] == 0.0             # tenant B's expense excluded


async def test_pnl_excludes_held_and_voided(client):
    """Held tickets and voided sales never count toward the P&L."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    await _seed_sale(client_id, user["id"], subtotal=100.0, vat=15.0, discount=0.0,
                     items=[{"product_id": 1, "name": "X", "price": 100.0, "quantity": 1, "cost_price": 40.0}],
                     invoice="OK")
    await _seed_sale(client_id, user["id"], subtotal=500.0, vat=75.0, discount=0.0,
                     items=[{"product_id": 1, "name": "X", "price": 500.0, "quantity": 1, "cost_price": 200.0}],
                     status="held", invoice="HELD")
    await _seed_sale(client_id, user["id"], subtotal=300.0, vat=45.0, discount=0.0,
                     items=[{"product_id": 1, "name": "X", "price": 300.0, "quantity": 1, "cost_price": 120.0}],
                     status="voided", invoice="VOID")

    body = (await client.get("/api/v1/reports/pnl?days=30", headers=headers)).json()
    assert abs(body["net_revenue"] - 100.0) < 0.01
    assert abs(body["cogs"] - 40.0) < 0.01


async def test_reports_require_client_role(client):
    """A non-client (agent) cannot reach the financial reports."""
    from conftest import make_agent_account
    _user, token, _agent_id = await make_agent_account(client)
    for path in ("pnl", "cash-flow"):
        resp = await client.get(f"/api/v1/reports/{path}?days=30", headers=auth_headers(token))
        assert resp.status_code == 403, f"{path}: {resp.text}"
