"""ISSUE-075 — Reprint past receipts.

A cashier must be able to look up a past sale and reprint its receipt,
re-rendering from the stored sale data through the same always-Arabic ESC/POS
renderer (template, totals and the canonical ZATCA QR all preserved).

A reprint is fiscally NOT a fresh issuance: the printed duplicate is stamped so
it cannot be mistaken for the original tax invoice, and every reprint is audited
(fraud control, mirroring the void audit trail). These tests pin:

* the renderer stamps a reprint marker while keeping the QR + Arabic raster body
  identical-in-kind to the original (AC2 "matches the original");
* the ``/escpos?reprint=true`` endpoint re-renders a past sale and records an
  audit row, while a normal print does neither (AC1/AC3).
"""
import base64

import pytest
from sqlalchemy import func, select

from conftest import auth_headers, make_client_account, add_product
from models.audit_logs import Audit_logs
from services.escpos import build_receipt

# GS ( k — QR-code command family; GS v 0 — raster bit-image (Arabic body).
QR_CMD = bytes([0x1D, 0x28, 0x6B])
RASTER_CMD = bytes([0x1D, 0x76, 0x30])


def _sample(**overrides) -> bytes:
    kwargs = dict(
        seller_name="Test Shop",
        vat_number="300000000000003",
        invoice_number="INV-0001-000001",
        issue_date="2026-06-02 10:00",
        line_items=[{"name": "Widget", "name_ar": "أداة", "price": 10.0, "quantity": 2, "discount": 0}],
        subtotal=20.0,
        discount=0.0,
        vat_amount=3.0,
        total_amount=23.0,
        zatca_qr="AQVTdG9yZQ==",
    )
    kwargs.update(overrides)
    return build_receipt(**kwargs)


def test_reprint_marks_duplicate_but_keeps_qr_and_raster():
    """A reprint stamps a distinguishing marker yet preserves the fiscal content:
    same Arabic raster body and the same canonical ZATCA QR (AC2)."""
    original = _sample(reprint=False)
    reprint = _sample(reprint=True)

    # The duplicate stamp changes the rendered bytes (so a reprint is visibly a
    # copy), and adds to — never strips — the body, which stays Arabic raster.
    assert reprint != original, "a reprint must be distinguishable from the original"
    assert RASTER_CMD in reprint, "reprint body must stay an Arabic raster"
    assert len(reprint) > len(original), "the duplicate marker lengthens the raster"

    # The fiscal QR still prints — the reprint matches the original tax content.
    assert QR_CMD in reprint, "reprint must carry the same canonical ZATCA QR"


def test_default_is_not_a_reprint():
    """Without the flag the receipt is the unchanged original (no marker)."""
    assert _sample() == _sample(reprint=False)


async def _make_sale(client, token, user_id, client_id):
    pid = await add_product(client_id, user_id, quantity=10, price=10.0)
    sale = await client.post(
        "/api/v1/pos/transaction",
        headers=auth_headers(token),
        json={
            "items": [{"product_id": pid, "name": "Widget", "price": 10.0, "quantity": 1}],
            "payment_method": "cash",
        },
    )
    assert sale.status_code in (200, 201), sale.text
    return sale.json()["id"]


@pytest.mark.asyncio
async def test_reprint_endpoint_rerenders_and_audits(client):
    """GET /escpos?reprint=true re-renders a past sale (Arabic raster + QR) AND
    records a POS_REPRINT_RECEIPT audit row for fraud control (AC1/AC3)."""
    from core.database import db_manager

    user, token, client_id = await make_client_account(client)
    txn_id = await _make_sale(client, token, user["id"], client_id)

    async with db_manager.async_session_maker() as session:
        before = (
            await session.execute(
                select(func.count(Audit_logs.id)).where(
                    Audit_logs.action == "POS_REPRINT_RECEIPT",
                    Audit_logs.entity_id == str(txn_id),
                )
            )
        ).scalar() or 0

    resp = await client.get(
        f"/api/v1/pos/transactions/{txn_id}/escpos?reprint=true",
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    raw = base64.b64decode(resp.json()["data"])
    assert RASTER_CMD in raw, "reprint still renders the Arabic raster body"
    assert QR_CMD in raw, "reprint carries the canonical ZATCA QR (matches original)"

    async with db_manager.async_session_maker() as session:
        after = (
            await session.execute(
                select(func.count(Audit_logs.id)).where(
                    Audit_logs.action == "POS_REPRINT_RECEIPT",
                    Audit_logs.entity_id == str(txn_id),
                )
            )
        ).scalar() or 0
    assert after == before + 1, "a reprint must be audited exactly once"


@pytest.mark.asyncio
async def test_normal_print_is_not_audited(client):
    """A first/normal print (no reprint flag) writes no reprint audit row."""
    from core.database import db_manager

    user, token, client_id = await make_client_account(client)
    txn_id = await _make_sale(client, token, user["id"], client_id)

    resp = await client.get(
        f"/api/v1/pos/transactions/{txn_id}/escpos", headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text

    async with db_manager.async_session_maker() as session:
        count = (
            await session.execute(
                select(func.count(Audit_logs.id)).where(
                    Audit_logs.action == "POS_REPRINT_RECEIPT",
                    Audit_logs.entity_id == str(txn_id),
                )
            )
        ).scalar() or 0
    assert count == 0, "a normal print must not be recorded as a reprint"
