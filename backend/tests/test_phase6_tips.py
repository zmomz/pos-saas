"""Phase 6 — POS-13 tips capture (F-012).

A sale can carry a **tip / gratuity** collected on top of the invoice total. A tip
is OUTSIDE the VAT base (it is not part of the taxable supply), so it never changes
the subtotal / VAT / total the ZATCA document is stamped on — it is recorded
separately, added to the amount the tenders must cover, and reported per shift in
the Z/X-report.

Catches forever (per the COMPLETENESS_REVIEW F-012 finding):
* a tipped sale: VAT is on the goods only, ``total_amount`` stays goods+VAT, the
  tip is stored, and the captured tender covers total + tip;
* a split payment must sum to the invoice total **plus** the tip (a split that
  only covers the invoice total is rejected);
* the tip shows up in the Z-report totals and in the cash drawer, but never
  inflates gross sales;
* a negative tip is rejected.
"""
from sqlalchemy import select

from conftest import add_product, auth_headers, make_client_account
from core.database import db_manager
from models.payment_tenders import PaymentTenders
from models.transactions import Transactions


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _open_shift(client, headers, opening_cash=0.0):
    resp = await client.post(
        "/api/v1/production/shifts/open",
        json={"opening_cash": opening_cash},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _tender_amounts(txn_id: int):
    async with db_manager.async_session_maker() as db:
        rows = (
            await db.execute(
                select(PaymentTenders).where(PaymentTenders.transaction_id == txn_id)
            )
        ).scalars().all()
        return {r.tender_type: r.amount for r in rows}


async def _stored_tip(txn_id: int) -> float:
    async with db_manager.async_session_maker() as db:
        # tip_amount is stored as Decimal (REV-03); coerce for float assertions.
        return float(
            (
                await db.execute(
                    select(Transactions.tip_amount).where(Transactions.id == txn_id)
                )
            ).scalar_one()
        )


# ---------------------------------------------------------------------------
# Tip is added to the amount due but excluded from the VAT base
# ---------------------------------------------------------------------------
async def test_tip_added_to_charge_total_and_excluded_from_vat(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=10, price=100.0)

    resp = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Cola", "price": 100.0, "quantity": 1}],
            "payment_method": "cash",
            "tip_amount": 10.0,
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # The tip is OUTSIDE the VAT base: VAT is 15% of the 100 goods only, and the
    # tax-invoice total stays goods+VAT — the tip does not touch it.
    assert abs(body["subtotal"] - 100.0) < 0.01
    assert abs(body["vat_amount"] - 15.0) < 0.01
    assert abs(body["total_amount"] - 115.0) < 0.01
    assert abs(body["tip_amount"] - 10.0) < 0.01

    # The tip is recorded on the row and the captured tender covers total + tip
    # (the customer actually paid 125), so it is not a label-only façade.
    assert abs(await _stored_tip(body["id"]) - 10.0) < 0.01
    tenders = await _tender_amounts(body["id"])
    assert abs(tenders["cash"] - 125.0) < 0.01


async def test_untipped_sale_has_no_tip(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=10, price=100.0)

    resp = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Cola", "price": 100.0, "quantity": 1}],
            "payment_method": "cash",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tip_amount"] is None
    tenders = await _tender_amounts(body["id"])
    assert abs(tenders["cash"] - 115.0) < 0.01


# ---------------------------------------------------------------------------
# A split payment must cover the invoice total PLUS the tip
# ---------------------------------------------------------------------------
async def test_split_payment_must_cover_invoice_plus_tip(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=10, price=100.0)

    base = {
        "items": [{"product_id": pid, "name": "Cola", "price": 100.0, "quantity": 1}],
        "payment_method": "mixed",
        "tip_amount": 10.0,
    }

    # Split that only covers the invoice total (115) ignores the 10 tip → due is 125.
    short = await client.post(
        "/api/v1/pos/transaction",
        json={**base, "payments": [{"method": "cash", "amount": 115.0}]},
        headers=headers,
    )
    assert short.status_code == 400, short.text
    assert "125" in short.json()["detail"]

    # Split that covers total + tip (cash 25 + transfer 100 = 125) is accepted.
    ok = await client.post(
        "/api/v1/pos/transaction",
        json={
            **base,
            "payments": [
                {"method": "cash", "amount": 25.0},
                {"method": "transfer", "amount": 100.0},
            ],
        },
        headers=headers,
    )
    assert ok.status_code == 200, ok.text
    assert abs(ok.json()["tip_amount"] - 10.0) < 0.01


async def test_negative_tip_rejected(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=10, price=100.0)

    resp = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Cola", "price": 100.0, "quantity": 1}],
            "payment_method": "cash",
            "tip_amount": -5.0,
        },
        headers=headers,
    )
    assert resp.status_code == 400, resp.text


# ---------------------------------------------------------------------------
# Tips surface in the Z-report but never inflate gross sales
# ---------------------------------------------------------------------------
async def test_tip_reported_in_zreport_and_excluded_from_gross_sales(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=10, price=100.0)

    await _open_shift(client, headers, opening_cash=0.0)
    sale = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Cola", "price": 100.0, "quantity": 1}],
            "payment_method": "cash",
            "tip_amount": 10.0,
        },
        headers=headers,
    )
    assert sale.status_code == 200, sale.text

    x = (await client.get("/api/v1/reports/zreport", headers=headers)).json()
    assert x["report_type"] == "X"
    # Tips are reported on their own line, outside the VAT base.
    assert abs(x["totals"]["tips"] - 10.0) < 0.01
    # Gross sales are the goods+VAT total only — the tip never inflates revenue.
    assert abs(x["totals"]["gross_sales"] - 115.0) < 0.01
    assert abs(x["totals"]["vat_collected"] - 15.0) < 0.01
    # The cash tender (and therefore the drawer) DID receive the tip: 115 + 10.
    tenders = {t["tender_type"]: t for t in x["tenders"]}
    assert abs(tenders["cash"]["amount"] - 125.0) < 0.01
    assert abs(x["cash"]["cash_sales"] - 125.0) < 0.01
    assert abs(x["cash"]["expected_cash"] - 125.0) < 0.01

    # The always-Arabic Z-report printable carries the tip line.
    doc = await client.get("/api/v1/reports/zreport/document", headers=headers)
    assert doc.status_code == 200, doc.text
    assert "البقشيش" in doc.text
