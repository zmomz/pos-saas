"""Phase 6 — PRN-08 subscription invoice (agent → client), part of F-053.

A paid subscription period is downloadable as an always-Arabic A4 PDF whose
required sections (seller block / buyer block / period / fee / VAT-if-registered
/ payment status) are present and ordered. The download is owner-scoped: a
client can only fetch invoices for their **own** subscription payments (SEC-02).
"""
import uuid

import pytest
from httpx import AsyncClient

from core.database import db_manager
from models.clients import Clients
from models.subscription_payments import Subscription_payments
from services import pdf_render

from conftest import auth_headers, make_client_account


# ---------------------------------------------------------------------------
# Golden-render contract on the pure row builder (no PDF parsing required).
# ---------------------------------------------------------------------------
def test_subscription_invoice_rows_have_seller_buyer_period_fee_and_status():
    rows = pdf_render.subscription_invoice_rows(
        seller_name="وكيل التجزئة",
        seller_vat="",  # agent not VAT-registered → VAT block omitted
        buyer_name="متجر العميل",
        buyer_vat="300000000000003",
        invoice_number="SUB-0001-000001",
        issue_date="2026-06-04",
        period_start="2026-06-04",
        period_end="2026-07-04",
        billing_cycle="monthly",
        fee=199.0,
        vat_amount=0.0,
        payment_status="paid",
        payment_method="manual",
    )
    kinds = [r[0] for r in rows]
    # Required sections present, in order: seller → buyer → ... → period → fee → total → status.
    assert "seller" in kinds and "buyer" in kinds
    assert "period" in kinds and "fee" in kinds and "status" in kinds
    assert kinds.index("seller") < kinds.index("buyer") < kinds.index("period")
    assert kinds.index("period") < kinds.index("fee") < kinds.index("status")
    # Seller VAT omitted when the agent is not registered (PRN-08 conditional);
    # the buyer VAT block IS rendered because the client carries a VAT number.
    assert "seller_vat" not in kinds
    assert "buyer_vat" in kinds
    # No VAT line when vat_amount == 0 (non-registered seller charges no VAT).
    assert "vat" not in kinds
    # The values carry the real seller/buyer/period/fee data.
    by_kind = {r[0]: r[2] for r in rows}
    assert by_kind["seller"] == "وكيل التجزئة"
    assert by_kind["buyer"] == "متجر العميل"
    assert "2026-06-04" in by_kind["period"] and "2026-07-04" in by_kind["period"]
    assert "199.00" in by_kind["fee"]


def test_subscription_invoice_renders_vat_block_when_seller_registered():
    rows = pdf_render.subscription_invoice_rows(
        seller_name="Agent",
        seller_vat="311111111111113",
        buyer_name="Client",
        buyer_vat="",
        invoice_number="SUB-0002-000002",
        issue_date="2026-06-04",
        period_start="2026-06-04",
        period_end="2026-07-04",
        billing_cycle="monthly",
        fee=100.0,
        vat_amount=15.0,
        payment_status="paid",
        payment_method="moyasar",
    )
    kinds = [r[0] for r in rows]
    assert "seller_vat" in kinds  # registered agent → seller VAT shown
    assert "vat" in kinds  # VAT charged → VAT line shown
    by_kind = {r[0]: r[2] for r in rows}
    # Total = fee + VAT.
    assert "115.00" in by_kind["total"]


def test_subscription_invoice_pdf_is_valid_and_embeds_arabic_font():
    data = pdf_render.subscription_invoice_pdf_bytes(
        seller_name="وكيل",
        buyer_name="عميل",
        invoice_number="SUB-0001-000001",
        issue_date="2026-06-04",
        period_start="2026-06-04",
        period_end="2026-07-04",
        billing_cycle="monthly",
        fee=199.0,
    )
    assert data[:5] == b"%PDF-"  # valid PDF magic
    assert len(data) > 1000
    # Amiri font embedded → the document is the always-Arabic layout (L10N-06).
    assert b"Amiri" in data


# ---------------------------------------------------------------------------
# Endpoint: download is owner-scoped (SEC-02).
# ---------------------------------------------------------------------------
async def _seed_payment(client_id: int, user_id: str, amount: float = 199.0) -> int:
    async with db_manager.async_session_maker() as db:
        pay = Subscription_payments(
            user_id=user_id,
            client_id=client_id,
            amount=amount,
            billing_cycle="monthly",
            period_start="2026-06-04",
            period_end="2026-07-04",
            method="manual",
        )
        db.add(pay)
        await db.commit()
        await db.refresh(pay)
        return pay.id


@pytest.mark.asyncio
async def test_client_downloads_own_subscription_invoice_pdf(client: AsyncClient):
    user, token, client_id = await make_client_account(client)
    # Give the buyer a VAT number so the buyer block renders it.
    async with db_manager.async_session_maker() as db:
        from sqlalchemy import update

        await db.execute(
            update(Clients).where(Clients.id == client_id).values(vat_number="300000000000003")
        )
        await db.commit()
    payment_id = await _seed_payment(client_id, user["id"])

    resp = await client.get(
        f"/api/v1/tenant/client/subscription/payments/{payment_id}/invoice",
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:5] == b"%PDF-"
    assert len(resp.content) > 1000


@pytest.mark.asyncio
async def test_client_cannot_download_another_clients_invoice(client: AsyncClient):
    owner, owner_token, owner_client_id = await make_client_account(client)
    payment_id = await _seed_payment(owner_client_id, owner["id"])

    # A different client must not be able to fetch the owner's invoice.
    _other, other_token, _other_id = await make_client_account(client)
    resp = await client.get(
        f"/api/v1/tenant/client/subscription/payments/{payment_id}/invoice",
        headers=auth_headers(other_token),
    )
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_non_client_cannot_download_subscription_invoice(client: AsyncClient):
    from conftest import make_master_account

    owner, _owner_token, owner_client_id = await make_client_account(client)
    payment_id = await _seed_payment(owner_client_id, owner["id"])

    _master, master_token = await make_master_account(client)
    resp = await client.get(
        f"/api/v1/tenant/client/subscription/payments/{payment_id}/invoice",
        headers=auth_headers(master_token),
    )
    # A non-client (master) has no subscription → 403 from _client_for_current_user.
    assert resp.status_code == 403, resp.text
