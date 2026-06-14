"""ISSUE-016 — gate Fatoora gateway submission + kill the divergent duplicate signer.

Until the fiscal substance (per-client PIH + signed UBL + C14N hash + persisted
UUID) is confirmed against a Fatoora sandbox, live gateway submission must be
**feature-flagged off** rather than silently POSTing invoices a real gateway
rejects. These tests assert:

  * submission is gated **off by default** — a fully onboarded client with a
    configured gateway still does **not** POST (the document fails closed to
    ``pending``) until ``zatca_live_submission_enabled`` is flipped on;
  * flipping the flag on restores real submission;
  * there is exactly **one** signer — the legacy in-router ``pos.py`` TLV/hash
    helpers are gone and the manual ``/sign`` endpoint delegates to the canonical
    ``services.zatca_sale.sign_transaction`` (so a manually signed document is the
    same gateway-valid signed UBL the sale path produces, not a divergent stub).
"""
import uuid

from sqlalchemy import select

from conftest import add_product, auth_headers, make_client_account
from core.database import db_manager
from models.clients import Clients
from models.transactions import Transactions
from models.zatca_credentials import ZatcaCredentials
from models.zatca_documents import ZatcaDocuments
from services import zatca, zatca_sale


async def _set_vat(client_id: int, vat: str = "300000000000003"):
    async with db_manager.async_session_maker() as db:
        row = (await db.execute(select(Clients).where(Clients.id == client_id))).scalar_one()
        row.vat_number = vat
        await db.commit()


async def _sale(client, headers, pid):
    resp = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Cola", "price": 10.0, "quantity": 1}],
            "payment_method": "cash",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _onboard_with_mock_gateway(client_id: int, monkeypatch):
    """Configure a mock Fatoora + onboard the client so the *only* thing left
    standing between us and a live POST is the submission gate. Returns a counter
    that records how many times the gateway's ``submit_invoice`` was actually hit.
    """
    monkeypatch.setattr(zatca, "resolve_base_url", lambda environment=None: "http://mock-fatoora")
    calls = {"n": 0}

    class _FakeApi:
        async def submit_invoice(self, **kwargs):
            calls["n"] += 1
            return {"reportingStatus": "REPORTED"}

    monkeypatch.setattr(
        zatca.ZatcaApiClient, "from_settings",
        classmethod(lambda cls, environment=None: _FakeApi()),
    )
    async with db_manager.async_session_maker() as db:
        creds = (
            await db.execute(select(ZatcaCredentials).where(ZatcaCredentials.client_id == client_id))
        ).scalar_one()
        creds.onboarded = True
        creds.production_csid = "csid-token"
        creds.production_secret_enc = zatca.encrypt_secret("prod-secret")
        await db.commit()
    return calls


async def _report_first_doc(client_id: int) -> str:
    async with db_manager.async_session_maker() as db:
        creds = (
            await db.execute(select(ZatcaCredentials).where(ZatcaCredentials.client_id == client_id))
        ).scalar_one()
        doc = (
            await db.execute(select(ZatcaDocuments).where(ZatcaDocuments.client_id == client_id))
        ).scalars().first()
        status = await zatca_sale.report_document(db, doc, creds)
        await db.commit()
        return status


# ---------------------------------------------------------------------------
# C2 gating
# ---------------------------------------------------------------------------
async def test_live_submission_gated_off_by_default(client, monkeypatch):
    """A fully onboarded client with a configured gateway must NOT POST while the
    submission flag is off (the default): the document fails closed to ``pending``
    and the gateway is never called."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _set_vat(client_id)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=10, price=10.0)
    await _sale(client, headers, pid)

    calls = await _onboard_with_mock_gateway(client_id, monkeypatch)

    # The gate is off by default — no flag set anywhere.
    assert zatca_sale.live_submission_enabled() is False

    status = await _report_first_doc(client_id)
    assert status == "pending"          # gated: archived but not posted
    assert calls["n"] == 0              # the gateway was never hit


async def test_live_submission_posts_when_flag_enabled(client, monkeypatch):
    """Flipping ``zatca_live_submission_enabled`` on restores real submission."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _set_vat(client_id)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=10, price=10.0)
    await _sale(client, headers, pid)

    calls = await _onboard_with_mock_gateway(client_id, monkeypatch)
    monkeypatch.setattr(zatca_sale.settings, "zatca_live_submission_enabled", True)

    status = await _report_first_doc(client_id)
    assert status == "reported"
    assert calls["n"] == 1


# ---------------------------------------------------------------------------
# Exactly one signer
# ---------------------------------------------------------------------------
def test_legacy_zatca_helpers_removed_from_pos_router():
    """The legacy in-router signer helpers are gone — there is one canonical
    signing path (``services.zatca_sale``)."""
    import routers.pos as pos

    assert not hasattr(pos, "generate_zatca_tlv")
    assert not hasattr(pos, "generate_zatca_hash")


async def test_manual_sign_endpoint_uses_canonical_signer(client):
    """The manual ``/sign`` endpoint must produce the *same* gateway-valid signed
    UBL the sale path does — proving it delegates to ``zatca_sale.sign_transaction``
    rather than re-implementing a divergent stub. The canonical document carries a
    persisted ``invoice_uuid`` and an enveloped XAdES signature inside
    ``UBLExtensions``; the old divergent path produced neither."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _set_vat(client_id)
    await client.post("/api/v1/zatca/onboard/csr", json={}, headers=headers)

    # Insert an unsigned transaction directly (no POS sale -> no auto-signed doc),
    # so the manual endpoint takes its *signing* branch, not the idempotent reuse.
    async with db_manager.async_session_maker() as db:
        txn = Transactions(
            user_id=str(user["id"]),
            client_id=client_id,
            invoice_number=f"INV-{uuid.uuid4().hex[:10]}",
            subtotal=10.0,
            vat_amount=1.5,
            total_amount=11.5,
            payment_method="cash",
            items_json="[]",
        )
        db.add(txn)
        await db.flush()
        txn_id = txn.id
        await db.commit()

    resp = await client.post(f"/api/v1/zatca/invoices/{txn_id}/sign", headers=headers)
    assert resp.status_code == 200, resp.text

    async with db_manager.async_session_maker() as db:
        doc = (
            await db.execute(select(ZatcaDocuments).where(ZatcaDocuments.transaction_id == txn_id))
        ).scalar_one()
        assert doc.invoice_uuid                          # persisted UUID (C2)
        signed = doc.signed_xml or ""
        assert "UBLExtensions" in signed                 # signed UBL, not the plain one
        assert "Signature" in signed                     # enveloped XAdES ds:Signature
