"""Slice 06 — sale-core extraction: one fiscal sale path.

The POS atomic sale (tender capture → invoice counter → inventory deduction incl.
BOM expansion → shift accumulation → ECDSA sign / hash-chain / archive, committed
together) used to live inline in the POS create-transaction handler. It now lives
once in ``services.sale_core.execute_sale`` so the restaurant settle path (F-059)
and aggregator ingest (F-060) mint an *identical* fiscal sale instead of forking
the compliance-critical logic three ways.

These tests exercise the extracted core **directly** (not through the POS HTTP
handler — that path is the regression guard in ``test_pos_atomic`` /
``test_phase2_zatca_sale``, which must pass unchanged). They prove the core:
mints a signed, stock-deducting sale from a ``NormalizedCart`` and returns the
persisted transaction + fiscal document; owns BOM expansion inside the atomic
stock transaction; and leaves nothing behind on any failure mid-sequence.
"""
import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from conftest import add_product, get_product_quantity, make_client_account
from core.database import db_manager
from models.clients import Clients
from models.transactions import Transactions
from models.zatca_documents import ZatcaDocuments
from routers.pos import CartItem
from services.restaurant import RestaurantService
from services.sale_core import NormalizedCart, execute_sale


async def _set_vat(client_id: int, vat: str = "300000000000003"):
    async with db_manager.async_session_maker() as db:
        row = (await db.execute(select(Clients).where(Clients.id == client_id))).scalar_one()
        row.vat_number = vat
        await db.commit()


async def _core_sale(client_id: int, user_id: str, lines, *, expand_bom=False, allow_negative_stock=False):
    """Mint a cash sale straight through the extracted sale core.

    Returns ``(transaction_id, document_id, invoice_number)`` read out before the
    session closes. Raises whatever ``execute_sale`` raises (e.g. a stock shortfall),
    leaving the session to roll back so the failure is atomic.
    """
    async with db_manager.async_session_maker() as db:
        client = (await db.execute(select(Clients).where(Clients.id == client_id))).scalar_one()
        subtotal = round(sum(l.price * l.quantity - (l.discount or 0) for l in lines), 2)
        vat_amount = round(subtotal * 0.15, 2)
        total = round(subtotal + vat_amount, 2)
        result = await execute_sale(
            db,
            NormalizedCart(
                user_id=user_id,
                client=client,
                lines=lines,
                subtotal=subtotal,
                discount_amount=0.0,
                vat_rate=15.0,
                vat_amount=vat_amount,
                total_amount=total,
                tender_specs=[{"tender_type": "cash", "amount": total}],
                payment_method="cash",
                expand_bom=expand_bom,
                allow_negative_stock=allow_negative_stock,
            ),
        )
        return (
            result.transaction.id,
            result.document_id,
            result.transaction.invoice_number,
        )


async def _txn_count(client_id: int) -> int:
    async with db_manager.async_session_maker() as db:
        return (
            await db.execute(
                select(func.count(Transactions.id)).where(Transactions.client_id == client_id)
            )
        ).scalar() or 0


async def _invoice_counter(client_id: int) -> int:
    async with db_manager.async_session_maker() as db:
        return (
            await db.execute(select(Clients.invoice_counter).where(Clients.id == client_id))
        ).scalar() or 0


# ---------------------------------------------------------------------------
# The core is a single reusable function: it mints a signed sale + fiscal doc.
# ---------------------------------------------------------------------------
async def test_core_mints_signed_sale_and_returns_fiscal_document(client):
    user, token, client_id = await make_client_account(client)
    await _set_vat(client_id)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=10, price=10.0)

    txn_id, doc_id, invoice_number = await _core_sale(
        client_id, user["id"], [CartItem(product_id=pid, name="Cola", price=10.0, quantity=3)]
    )

    # Returns the persisted transaction…
    assert txn_id and invoice_number.startswith(f"INV-{client_id:04d}-")
    # …and the fiscal document (signed + archived, linked to the transaction).
    assert doc_id is not None
    async with db_manager.async_session_maker() as db:
        doc = (await db.execute(select(ZatcaDocuments).where(ZatcaDocuments.id == doc_id))).scalar_one()
        assert doc.document_type == "invoice"
        assert doc.transaction_id == txn_id
        assert doc.status == "signed"
        assert doc.stamp  # a real ECDSA stamp was produced
    # Stock was deducted in the same atomic transaction.
    assert await get_product_quantity(pid) == 7


# ---------------------------------------------------------------------------
# The sale core owns BOM expansion inside the atomic stock transaction (F-062).
# ---------------------------------------------------------------------------
async def test_core_expands_bom_and_depletes_components(client):
    user, token, client_id = await make_client_account(client, business_type="restaurant")
    await _set_vat(client_id)
    burger = await add_product(client_id, user["id"], name="Burger", quantity=100, price=25.0)
    patty = await add_product(client_id, user["id"], name="Patty", quantity=10, price=0.0)

    async with db_manager.async_session_maker() as db:
        svc = RestaurantService(db)
        await svc.create_bom_entry(
            burger, {"component_product_id": patty, "qty_per": 2}, user["id"], client_id
        )

    # Sell 3 burgers with BOM expansion on: 3 × 2 = 6 patties depleted, atomically.
    _txn, doc_id, _inv = await _core_sale(
        client_id,
        user["id"],
        [CartItem(product_id=burger, name="Burger", price=25.0, quantity=3)],
        expand_bom=True,
    )
    assert doc_id is not None
    assert await get_product_quantity(patty) == 4      # 10 - (2 × 3)
    assert await get_product_quantity(burger) == 97     # the finished line still deducts


async def test_core_bom_shortfall_rolls_back_entire_sale(client):
    """A component shortfall during BOM expansion raises before commit, so the
    whole sale rolls back: no orphan invoice, no consumed counter, and NO partial
    stock deduction (not the finished line, not the components)."""
    user, token, client_id = await make_client_account(client, business_type="restaurant")
    await _set_vat(client_id)
    burger = await add_product(client_id, user["id"], name="Burger", quantity=100, price=25.0)
    patty = await add_product(client_id, user["id"], name="Patty", quantity=1, price=0.0)

    async with db_manager.async_session_maker() as db:
        svc = RestaurantService(db)
        await svc.create_bom_entry(
            burger, {"component_product_id": patty, "qty_per": 2}, user["id"], client_id
        )

    before_count = await _txn_count(client_id)
    before_counter = await _invoice_counter(client_id)

    # 1 burger needs 2 patties but only 1 is in stock → shortfall.
    with pytest.raises(HTTPException) as exc:
        await _core_sale(
            client_id,
            user["id"],
            [CartItem(product_id=burger, name="Burger", price=25.0, quantity=1)],
            expand_bom=True,
        )
    assert exc.value.status_code == 400

    # Atomic: nothing persisted, nothing deducted.
    assert await _txn_count(client_id) == before_count
    assert await _invoice_counter(client_id) == before_counter
    assert await get_product_quantity(burger) == 100   # finished line NOT deducted
    assert await get_product_quantity(patty) == 1       # component NOT deducted
