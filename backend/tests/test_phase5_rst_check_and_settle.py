"""F-059 — Check + settle-to-ZATCA.

Two steps close the loop a restaurant cannot today — turning an order ticket into
money and a compliant invoice:

1. **Check (non-fiscal):** ``POST …/order-tickets/{id}/check`` prints an 80mm
   always-Arabic proforma marked *فاتورة مبدئية* with **no QR and no stamp**, so
   the customer reviews the bill before paying and it can never be mistaken for a
   tax invoice.
2. **Settle (fiscal):** ``POST …/order-tickets/{id}/settle`` builds a normalized
   cart from the ticket (lines + modifiers + combos + service charge + BOM
   components) and mints a real ZATCA invoice through the **same** atomic sale core
   (``services.sale_core.execute_sale``) the POS uses. On success the ticket is
   ``settled`` and the table freed.

Settlement is atomic: a **declined card rolls the whole thing back** — the ticket
stays ``open``, the table stays occupied, and **no invoice is minted**. A
restaurant sale must be byte-for-byte as compliant as a retail sale.

The named "catch-forever" tests required by the slice are
``test_check_is_non_fiscal_no_qr``,
``test_settle_creates_zatca_invoice_and_frees_table`` and the settlement-rollback
test (declined card → ticket still open, no invoice).
"""
from sqlalchemy import func, select

from conftest import (
    add_product,
    auth_headers,
    get_product_quantity,
    make_client_account,
)
from core.database import db_manager
from models.clients import Clients
from models.transactions import Transactions
from models.zatca_documents import ZatcaDocuments


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _set_vat(client_id: int, vat: str = "300000000000003"):
    async with db_manager.async_session_maker() as db:
        row = (await db.execute(select(Clients).where(Clients.id == client_id))).scalar_one()
        row.vat_number = vat
        await db.commit()


async def _make_table(client, token, name="T1"):
    return (
        await client.post(
            "/api/v1/restaurant/tables",
            json={"name": name, "seats": 4},
            headers=auth_headers(token),
        )
    ).json()["id"]


async def _open_dine_in(client, token, table_id):
    resp = await client.post(
        "/api/v1/restaurant/order-tickets",
        json={"order_type": "dine_in", "table_id": table_id},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _add_line(client, token, ticket_id, product_id, qty=1):
    resp = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/items",
        json={"product_id": product_id, "qty": qty},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _table_state(client, token, table_id) -> str:
    resp = await client.get(
        f"/api/v1/restaurant/tables/{table_id}", headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["state"]


async def _doc_count(client_id: int) -> int:
    async with db_manager.async_session_maker() as db:
        return (
            await db.execute(
                select(func.count(ZatcaDocuments.id)).where(
                    ZatcaDocuments.client_id == client_id
                )
            )
        ).scalar() or 0


async def _txn_count(client_id: int) -> int:
    async with db_manager.async_session_maker() as db:
        return (
            await db.execute(
                select(func.count(Transactions.id)).where(
                    Transactions.client_id == client_id
                )
            )
        ).scalar() or 0


# ---------------------------------------------------------------------------
# Named slice test: the check is a non-fiscal proforma — no QR, no stamp.
# ---------------------------------------------------------------------------
async def test_check_is_non_fiscal_no_qr(client):
    user, token, client_id = await make_client_account(client, business_type="restaurant")
    headers = auth_headers(token)
    table_id = await _make_table(client, token, name="C1")
    ticket_id = await _open_dine_in(client, token, table_id)
    pid = await add_product(client_id, user["id"], name="Shawarma", quantity=50, price=40.0)
    await _add_line(client, token, ticket_id, pid, qty=2)

    resp = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/check",
        json={},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Marked as a proforma (فاتورة مبدئية) and explicitly non-fiscal.
    assert body["document_type"] == "proforma"
    assert body["title_ar"] == "فاتورة مبدئية"
    assert body["is_fiscal"] is False
    # The defining invariant: no QR and no stamp on a check.
    assert body["has_qr"] is False
    assert body["has_stamp"] is False
    assert "zatca_qr" not in body
    # It still carries the full breakdown the customer reviews.
    assert abs(body["subtotal"] - 80.0) < 0.01
    assert abs(body["vat_amount"] - 12.0) < 0.01
    assert abs(body["amount_due"] - 92.0) < 0.01
    # An 80mm proforma was rendered (base64 ESC/POS body).
    assert body["proforma_base64"]

    # Printing a check has NO fiscal side effects: nothing is minted and the
    # ticket stays open. The floor reflects that a bill is out (bill_printed),
    # but no invoice/transaction exists yet.
    assert await _doc_count(client_id) == 0
    assert await _txn_count(client_id) == 0
    assert await _table_state(client, token, table_id) == "bill_printed"


# ---------------------------------------------------------------------------
# Named slice test: printing the check persists the bill_printed table state.
# ---------------------------------------------------------------------------
async def test_printing_check_sets_table_bill_printed(client):
    """Printing the proforma flips the dine-in table occupied -> bill_printed (U4.1).

    The floor's ``bill_printed`` state was rendered/translated but never assigned
    server-side, so the tile only flipped in the browser — another device or a
    page reload still saw ``occupied``. Printing the check must persist the state
    so every session sees the real floor.
    """
    user, token, client_id = await make_client_account(client, business_type="restaurant")
    headers = auth_headers(token)
    table_id = await _make_table(client, token, name="BP1")
    ticket_id = await _open_dine_in(client, token, table_id)
    pid = await add_product(client_id, user["id"], name="Mandi", quantity=30, price=55.0)
    await _add_line(client, token, ticket_id, pid, qty=1)

    assert await _table_state(client, token, table_id) == "occupied"

    resp = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/check",
        json={},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    # Persisted server-side: a FRESH read (another device/session) sees it.
    assert await _table_state(client, token, table_id) == "bill_printed"
    # The ticket itself stays open — printing a check is not settling.
    tk = await client.get(
        f"/api/v1/restaurant/order-tickets/{ticket_id}", headers=headers
    )
    assert tk.json()["status"] == "open"


# ---------------------------------------------------------------------------
# Named slice test: settle mints a real ZATCA invoice and frees the table.
# ---------------------------------------------------------------------------
async def test_settle_creates_zatca_invoice_and_frees_table(client):
    user, token, client_id = await make_client_account(client, business_type="restaurant")
    await _set_vat(client_id)
    headers = auth_headers(token)
    table_id = await _make_table(client, token, name="S1")
    ticket_id = await _open_dine_in(client, token, table_id)
    pid = await add_product(client_id, user["id"], name="Mixed Grill", quantity=20, price=100.0)
    await _add_line(client, token, ticket_id, pid, qty=1)

    # 10% service charge — outside the VAT base.
    await client.put(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/service-charge",
        json={"service_charge_pct": 10},
        headers=headers,
    )

    assert await _table_state(client, token, table_id) == "occupied"

    # Settle for cash. amount_due = 100 goods + 15 VAT + 10 service charge = 125.
    resp = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/settle",
        json={"payment_method": "cash"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # A real ZATCA invoice was minted via the sale core: signed doc + stamped QR.
    assert body["invoice_number"].startswith(f"INV-{client_id:04d}-")
    assert body["zatca_document_id"] is not None
    assert body["zatca_status"] == "signed"
    assert body["zatca_qr"]  # a real ECDSA-stamped TLV QR
    assert body["zatca_qr_base64"]
    # Service charge appears outside the VAT base; amounts add up.
    assert abs(body["subtotal"] - 100.0) < 0.01
    assert abs(body["vat_amount"] - 15.0) < 0.01
    assert abs(body["service_charge"] - 10.0) < 0.01
    assert abs(body["amount_due"] - 125.0) < 0.01

    # The settled invoice's signed document is real + linked to the transaction.
    async with db_manager.async_session_maker() as db:
        doc = (
            await db.execute(
                select(ZatcaDocuments).where(
                    ZatcaDocuments.id == body["zatca_document_id"]
                )
            )
        ).scalar_one()
        assert doc.document_type == "invoice"
        assert doc.transaction_id == body["transaction_id"]
        # Signed at mint time; the post-commit background reporting job then moves
        # it on (fail-closed to "pending" on an un-onboarded gateway). What matters
        # is a real ECDSA stamp was produced and the document is archived.
        assert doc.status in ("signed", "pending", "reported", "cleared")
        assert doc.stamp

    # The ticket is settled and the table is freed.
    assert body["ticket_status"] == "settled"
    assert body["table_freed"] is True
    tk = await client.get(
        f"/api/v1/restaurant/order-tickets/{ticket_id}", headers=headers
    )
    assert tk.json()["status"] == "settled"
    assert await _table_state(client, token, table_id) == "free"
    # Stock was deducted in the same atomic sale.
    assert await get_product_quantity(pid) == 19


# ---------------------------------------------------------------------------
# Named slice test: a declined card rolls the whole settlement back.
# ---------------------------------------------------------------------------
async def test_settle_declined_card_rolls_back_no_invoice(client):
    user, token, client_id = await make_client_account(client, business_type="restaurant")
    await _set_vat(client_id)
    headers = auth_headers(token)
    table_id = await _make_table(client, token, name="D1")
    ticket_id = await _open_dine_in(client, token, table_id)
    pid = await add_product(client_id, user["id"], name="Kabsa", quantity=15, price=60.0)
    await _add_line(client, token, ticket_id, pid, qty=1)

    before_docs = await _doc_count(client_id)
    before_txns = await _txn_count(client_id)

    # A sandbox-forced card decline at settlement.
    resp = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/settle",
        json={"payment_method": "mada", "payment_simulate": "decline"},
        headers=headers,
    )
    # Decline → 402 Payment Required, nothing committed.
    assert resp.status_code == 402, resp.text

    # Atomic rollback: no invoice minted, no transaction, no fiscal document.
    assert await _doc_count(client_id) == before_docs
    assert await _txn_count(client_id) == before_txns
    # The ticket stays open and the table stays occupied.
    tk = await client.get(
        f"/api/v1/restaurant/order-tickets/{ticket_id}", headers=headers
    )
    assert tk.json()["status"] == "open"
    assert await _table_state(client, token, table_id) == "occupied"
    # Stock untouched (the sale never deducted).
    assert await get_product_quantity(pid) == 15


# ---------------------------------------------------------------------------
# Settle depletes BOM components through the same atomic path (F-062 reuse).
# ---------------------------------------------------------------------------
async def test_settle_depletes_bom_components(client):
    user, token, client_id = await make_client_account(client, business_type="restaurant")
    await _set_vat(client_id)
    headers = auth_headers(token)
    table_id = await _make_table(client, token, name="B1")
    ticket_id = await _open_dine_in(client, token, table_id)
    burger = await add_product(client_id, user["id"], name="Burger", quantity=100, price=25.0)
    patty = await add_product(client_id, user["id"], name="Patty", quantity=10, price=0.0)

    # 2 patties per burger.
    bom = await client.post(
        f"/api/v1/restaurant/products/{burger}/bom",
        json={"component_product_id": patty, "qty_per": 2},
        headers=headers,
    )
    assert bom.status_code == 201, bom.text

    await _add_line(client, token, ticket_id, burger, qty=3)
    resp = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/settle",
        json={"payment_method": "cash"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    # The finished line deducts AND the recipe expands: 3 burgers → 6 patties.
    assert await get_product_quantity(burger) == 97
    assert await get_product_quantity(patty) == 4


# ---------------------------------------------------------------------------
# A settled ticket cannot be settled again (guards double-billing).
# ---------------------------------------------------------------------------
async def test_settle_twice_is_rejected(client):
    user, token, client_id = await make_client_account(client, business_type="restaurant")
    await _set_vat(client_id)
    headers = auth_headers(token)
    table_id = await _make_table(client, token, name="T2")
    ticket_id = await _open_dine_in(client, token, table_id)
    pid = await add_product(client_id, user["id"], name="Falafel", quantity=20, price=10.0)
    await _add_line(client, token, ticket_id, pid, qty=1)

    first = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/settle",
        json={"payment_method": "cash"},
        headers=headers,
    )
    assert first.status_code == 200, first.text

    again = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/settle",
        json={"payment_method": "cash"},
        headers=headers,
    )
    assert again.status_code == 409, again.text


# ---------------------------------------------------------------------------
# Settling a combo deducts each component product's stock (ISSUE-032, H23).
# A combo line carries product_id=None and priced at its bundle price; without
# expansion the sale charges the bundle but decrements NO stock (silent oversell).
# ---------------------------------------------------------------------------
async def test_settle_depletes_combo_components(client):
    user, token, client_id = await make_client_account(client, business_type="restaurant")
    await _set_vat(client_id)
    headers = auth_headers(token)
    table_id = await _make_table(client, token, name="C1")
    ticket_id = await _open_dine_in(client, token, table_id)
    burger = await add_product(client_id, user["id"], name="Burger", quantity=20, price=30.0)
    fries = await add_product(client_id, user["id"], name="Fries", quantity=20, price=12.0)
    drink = await add_product(client_id, user["id"], name="Cola", quantity=20, price=8.0)

    # A meal: 1 burger + 1 fries + 2 drinks, sold as a bundle for 39.
    combo = await client.post(
        "/api/v1/restaurant/combos",
        json={
            "name": "Meal Deal",
            "bundle_price": 39.0,
            "components": [
                {"product_id": burger, "qty": 1},
                {"product_id": fries, "qty": 1},
                {"product_id": drink, "qty": 2},
            ],
        },
        headers=headers,
    )
    assert combo.status_code == 201, combo.text

    # Two meals on the ticket.
    line = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/items",
        json={"combo_id": combo.json()["id"], "qty": 2},
        headers=headers,
    )
    assert line.status_code == 201, line.text

    resp = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/settle",
        json={"payment_method": "cash"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    # Each component deducts exactly once: qty_per × 2 meals.
    assert await get_product_quantity(burger) == 18  # 20 - 1*2
    assert await get_product_quantity(fries) == 18  # 20 - 1*2
    assert await get_product_quantity(drink) == 16  # 20 - 2*2


# ---------------------------------------------------------------------------
# A combo whose component is BOM-backed deducts the component AND its recipe,
# each exactly once — combo expansion composes with BOM without double-counting
# (ISSUE-032 AC2/AC3, coordinates with the deplete-double-deduct trap #104).
# ---------------------------------------------------------------------------
async def test_settle_combo_component_bom_deducts_once(client):
    user, token, client_id = await make_client_account(client, business_type="restaurant")
    await _set_vat(client_id)
    headers = auth_headers(token)
    table_id = await _make_table(client, token, name="C2")
    ticket_id = await _open_dine_in(client, token, table_id)
    burger = await add_product(client_id, user["id"], name="Burger", quantity=100, price=25.0)
    patty = await add_product(client_id, user["id"], name="Patty", quantity=10, price=0.0)

    # The burger is itself BOM-backed: 2 patties per burger.
    bom = await client.post(
        f"/api/v1/restaurant/products/{burger}/bom",
        json={"component_product_id": patty, "qty_per": 2},
        headers=headers,
    )
    assert bom.status_code == 201, bom.text

    # A combo of 1 burger, three meals on the ticket.
    combo = await client.post(
        "/api/v1/restaurant/combos",
        json={
            "name": "Burger Combo",
            "bundle_price": 20.0,
            "components": [{"product_id": burger, "qty": 1}],
        },
        headers=headers,
    )
    assert combo.status_code == 201, combo.text
    line = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/items",
        json={"combo_id": combo.json()["id"], "qty": 3},
        headers=headers,
    )
    assert line.status_code == 201, line.text

    resp = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/settle",
        json={"payment_method": "cash"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    # Burger deducts once (3), and its recipe expands once (3×2 = 6 patties) —
    # not twice. No double-count when combo expansion meets BOM depletion.
    assert await get_product_quantity(burger) == 97  # 100 - 3
    assert await get_product_quantity(patty) == 4  # 10 - 6


# ---------------------------------------------------------------------------
# A split settlement whose tenders don't sum to amount_due is rejected.
# ---------------------------------------------------------------------------
async def test_settle_split_mismatch_rejected(client):
    user, token, client_id = await make_client_account(client, business_type="restaurant")
    await _set_vat(client_id)
    headers = auth_headers(token)
    table_id = await _make_table(client, token, name="T3")
    ticket_id = await _open_dine_in(client, token, table_id)
    pid = await add_product(client_id, user["id"], name="Juice", quantity=20, price=100.0)
    await _add_line(client, token, ticket_id, pid, qty=1)

    # amount_due = 115.00; tenders sum to 100.00 → mismatch.
    resp = await client.post(
        f"/api/v1/restaurant/order-tickets/{ticket_id}/settle",
        json={
            "payment_method": "mixed",
            "payments": [
                {"method": "cash", "amount": 50.0},
                {"method": "cash", "amount": 50.0},
            ],
        },
        headers=headers,
    )
    assert resp.status_code == 400, resp.text
    # The ticket was not settled.
    tk = await client.get(
        f"/api/v1/restaurant/order-tickets/{ticket_id}", headers=headers
    )
    assert tk.json()["status"] == "open"
