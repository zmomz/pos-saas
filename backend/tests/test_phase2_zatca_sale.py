"""Phase 2 — ZATCA compliance on the real sale path (C-3, C-4, POS-07, ZA-04).

Proves that every POS sale is signed/stamped/chained, that the fiscal QR is a
real stamped TLV rendered to a PNG, that refunds issue compliant 381 credit
notes (restoring stock + chaining), that Fatoora reporting retries transient
failures and fails closed when unconfigured, and that the chain+signature
integrity endpoint validates the whole chain.
"""
import base64
import uuid

from sqlalchemy import select

from conftest import add_product, auth_headers, get_product_quantity, make_client_account
from core.database import db_manager
from models.clients import Clients
from models.transactions import Transactions
from models.zatca_credentials import ZatcaCredentials
from models.zatca_documents import ZatcaDocuments
from services import zatca, zatca_sale


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _set_vat(client_id: int, vat: str = "300000000000003"):
    async with db_manager.async_session_maker() as db:
        row = (await db.execute(select(Clients).where(Clients.id == client_id))).scalar_one()
        row.vat_number = vat
        await db.commit()


async def _sale(client, headers, pid, *, name="Cola", price=10.0, qty=2):
    resp = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": name, "price": price, "quantity": qty}],
            "payment_method": "cash",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _docs(client_id: int):
    async with db_manager.async_session_maker() as db:
        rows = (
            await db.execute(
                select(ZatcaDocuments)
                .where(ZatcaDocuments.client_id == client_id)
                .order_by(ZatcaDocuments.icv.asc())
            )
        ).scalars().all()
        # Detach plain copies so callers can read after the session closes.
        return [
            {
                "id": d.id,
                "transaction_id": d.transaction_id,
                "document_type": d.document_type,
                "icv": d.icv,
                "invoice_hash": d.invoice_hash,
                "previous_hash": d.previous_hash,
                "stamp": d.stamp,
                "signed_xml": d.signed_xml,
                "status": d.status,
            }
            for d in rows
        ]


async def _client_pubkey(client_id: int) -> str:
    async with db_manager.async_session_maker() as db:
        creds = (
            await db.execute(
                select(ZatcaCredentials).where(ZatcaCredentials.client_id == client_id)
            )
        ).scalar_one()
        key_pem = zatca.decrypt_secret(creds.private_key_enc)
        return zatca.public_key_pem_from_private(key_pem)


# ---------------------------------------------------------------------------
# Unit: stamped TLV (tags 1-8)
# ---------------------------------------------------------------------------
def test_stamped_tlv_carries_tags_1_to_8():
    key_pem, _ = zatca.generate_egs_keypair_and_csr(
        common_name="A", organization_name="A", organization_unit="1",
        vat_number="300000000000003", egs_serial="1-A|2-B|3-C",
    )
    inv_hash = zatca.invoice_hash_b64(b"<Invoice/>")
    stamp = zatca.sign_invoice_hash(key_pem, inv_hash)
    tlv = zatca.build_stamped_qr_tlv(
        seller_name="Acme", vat_number="300000000000003",
        timestamp="2026-06-02T10:00:00+00:00", total_with_vat="23.00", vat_amount="3.00",
        invoice_hash_b64=inv_hash, stamp_b64=stamp,
        public_key_der_base64=zatca.public_key_der_b64(key_pem),
    )
    tags = zatca.parse_tlv_tags(tlv)
    assert set(range(1, 9)).issubset(tags.keys())
    assert tags[1] == b"Acme"
    assert tags[6] == base64.b64decode(inv_hash)   # tag 6 = invoice hash bytes
    assert tags[7] == base64.b64decode(stamp)       # tag 7 = ECDSA signature


# ---------------------------------------------------------------------------
# C-3 / C-4: a real sale is signed, stamped, archived, QR rendered
# ---------------------------------------------------------------------------
async def test_sale_is_signed_stamped_and_qr_rendered(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _set_vat(client_id)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=10, price=10.0)

    body = await _sale(client, headers, pid)

    # Response carries the fiscal linkage + a renderable QR PNG.
    assert body["zatca_document_id"]
    assert body["zatca_status"] == "signed"
    png = base64.b64decode(body["zatca_qr_base64"])
    assert png[:8] == b"\x89PNG\r\n\x1a\n"          # real PNG image (C-4)

    # The QR is the stamped TLV with all 8 ZATCA tags.
    tags = zatca.parse_tlv_tags(body["zatca_qr"])
    assert set(range(1, 9)).issubset(tags.keys())

    # Exactly one archived document, with a stamp that verifies (real ECDSA).
    docs = await _docs(client_id)
    assert len(docs) == 1
    doc = docs[0]
    assert doc["document_type"] == "invoice"
    assert doc["transaction_id"] == body["id"]
    pub = await _client_pubkey(client_id)
    assert zatca.verify_stamp(pub, doc["invoice_hash"], doc["stamp"])
    # tag 6 in the QR re-hashes to the archived invoice hash.
    assert tags[6] == base64.b64decode(doc["invoice_hash"])


async def test_two_sales_chain_previous_hash(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _set_vat(client_id)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=50, price=5.0)

    await _sale(client, headers, pid)
    await _sale(client, headers, pid)

    docs = await _docs(client_id)
    assert len(docs) == 2
    assert docs[0]["previous_hash"] == zatca.INITIAL_PIH
    # ZA-04: the 2nd invoice chains onto the 1st invoice's hash.
    assert docs[1]["previous_hash"] == docs[0]["invoice_hash"]
    assert docs[0]["icv"] == 1 and docs[1]["icv"] == 2


# ---------------------------------------------------------------------------
# ZA-04: integrity endpoint validates the chain + every stamp
# ---------------------------------------------------------------------------
async def test_integrity_endpoint_validates_chain(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _set_vat(client_id)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=50, price=5.0)
    await _sale(client, headers, pid)
    await _sale(client, headers, pid)

    resp = await client.get("/api/v1/zatca/integrity", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["total"] == 2
    assert body["chain_ok"] and body["signatures_ok"]
    assert body["broken_at"] is None


async def test_integrity_detects_tampering(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _set_vat(client_id)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=50, price=5.0)
    await _sale(client, headers, pid)

    # Tamper with the archived hash so the chain seed no longer matches.
    async with db_manager.async_session_maker() as db:
        doc = (
            await db.execute(select(ZatcaDocuments).where(ZatcaDocuments.client_id == client_id))
        ).scalars().first()
        doc.previous_hash = "tampered=="
        await db.commit()

    resp = await client.get("/api/v1/zatca/integrity", headers=headers)
    body = resp.json()
    assert body["ok"] is False
    assert body["chain_ok"] is False


# ---------------------------------------------------------------------------
# POS-07: refund issues a compliant 381 credit note
# ---------------------------------------------------------------------------
async def test_refund_creates_credit_note_and_restores_stock(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _set_vat(client_id)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=10, price=10.0)

    sale = await _sale(client, headers, pid, qty=3)
    assert await get_product_quantity(pid) == 7   # 10 - 3 sold

    resp = await client.post(
        f"/api/v1/pos/transactions/{sale['id']}/refund", headers=headers
    )
    assert resp.status_code == 200, resp.text
    refund = resp.json()
    assert refund["credit_note_number"].startswith("CRN-")
    assert refund["original_transaction_id"] == sale["id"]
    assert refund["total_amount"] < 0             # credit note nets negative
    assert base64.b64decode(refund["zatca_qr_base64"])[:4] == b"\x89PNG"

    # Inventory restored.
    assert await get_product_quantity(pid) == 10

    docs = await _docs(client_id)
    assert len(docs) == 2
    invoice_doc, credit_doc = docs[0], docs[1]
    assert credit_doc["document_type"] == "credit_note"
    # 381 + billing reference to the original invoice number in the signed XML.
    assert "381" in credit_doc["signed_xml"]
    assert sale["invoice_number"] in credit_doc["signed_xml"]
    # Credit note chains onto the original invoice's hash.
    assert credit_doc["previous_hash"] == invoice_doc["invoice_hash"]
    # Stamp verifies.
    pub = await _client_pubkey(client_id)
    assert zatca.verify_stamp(pub, credit_doc["invoice_hash"], credit_doc["stamp"])


async def test_double_refund_is_rejected(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _set_vat(client_id)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=10, price=10.0)
    sale = await _sale(client, headers, pid, qty=1)

    first = await client.post(f"/api/v1/pos/transactions/{sale['id']}/refund", headers=headers)
    assert first.status_code == 200
    second = await client.post(f"/api/v1/pos/transactions/{sale['id']}/refund", headers=headers)
    assert second.status_code == 400
    assert "already refunded" in second.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Reporting: retry on 5xx, fail closed to "pending" when unconfigured
# ---------------------------------------------------------------------------
async def test_reporting_retries_on_5xx_then_reports(client, monkeypatch):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _set_vat(client_id)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=10, price=10.0)
    await _sale(client, headers, pid)

    # Configure a (mock) gateway and stub the HTTP client so no network is hit.
    monkeypatch.setattr(zatca, "resolve_base_url", lambda environment=None: "http://mock-fatoora")
    calls = {"n": 0}

    class _FakeApi:
        async def submit_invoice(self, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise zatca.ZatcaApiError("upstream 500", status_code=500, error_type="gateway")
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
        doc = (
            await db.execute(select(ZatcaDocuments).where(ZatcaDocuments.client_id == client_id))
        ).scalars().first()
        status = await zatca_sale.report_document(db, doc, creds)
        await db.commit()

    assert status == "reported"
    assert calls["n"] == 2          # one transient failure, retried, then success


async def test_reporting_fails_closed_to_pending_when_unconfigured(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _set_vat(client_id)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=10, price=10.0)
    await _sale(client, headers, pid)

    # No gateway / not onboarded -> reporting must not raise; doc -> "pending".
    async with db_manager.async_session_maker() as db:
        creds = (
            await db.execute(select(ZatcaCredentials).where(ZatcaCredentials.client_id == client_id))
        ).scalar_one()
        doc = (
            await db.execute(select(ZatcaDocuments).where(ZatcaDocuments.client_id == client_id))
        ).scalars().first()
        status = await zatca_sale.report_document(db, doc, creds)
        await db.commit()
    assert status == "pending"


# ---------------------------------------------------------------------------
# ZA-06 (F-017): B2B clearance vs B2C reporting routing
# ---------------------------------------------------------------------------
async def _sign_synthetic(client_id: int, user_id, *, buyer_vat, total: float):
    """Sign a standalone transaction with a given buyer VAT + total.

    Returns (doc_id, invoice_subtype, signed_xml). Exercises ``sign_transaction``
    directly so the routing can be driven independently of the (F-018) buyer-VAT
    capture on the sale path.
    """
    async with db_manager.async_session_maker() as db:
        client_row = (
            await db.execute(select(Clients).where(Clients.id == client_id))
        ).scalar_one()
        sub = round(total / 1.15, 2)
        txn = Transactions(
            user_id=str(user_id),
            client_id=client_id,
            invoice_number=f"INV-{uuid.uuid4().hex[:10]}",
            subtotal=sub,
            vat_amount=round(total - sub, 2),
            total_amount=total,
            payment_method="cash",
            items_json="[]",
        )
        db.add(txn)
        await db.flush()
        doc, _ = await zatca_sale.sign_transaction(db, client_row, txn, buyer_vat=buyer_vat)
        result = (doc.id, doc.invoice_subtype, doc.signed_xml)
        await db.commit()
        return result


async def _report_capturing_clearance(client_id: int, doc_id: int, monkeypatch):
    """Report a signed doc through a mock *onboarded* gateway.

    Returns (status, clearance_used) where ``clearance_used`` is the clearance flag
    the routing passed to ``submit_invoice`` (derived from the doc's subtype, since
    the background path supplies no explicit clearance).
    """
    captured: dict = {}

    class _FakeApi:
        async def submit_invoice(self, **kwargs):
            captured["clearance"] = kwargs.get("clearance")
            return {"status": "OK"}

    monkeypatch.setattr(zatca, "resolve_base_url", lambda environment=None: "http://mock-fatoora")
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
        doc = (
            await db.execute(select(ZatcaDocuments).where(ZatcaDocuments.id == doc_id))
        ).scalar_one()
        status = await zatca_sale.report_document(db, doc, creds)  # clearance from subtype
        await db.commit()
    return status, captured.get("clearance")


def test_classify_invoice_subtype_routing():
    # B2B (buyer VAT) at/above the 1,000-SAR threshold -> standard (clearance).
    assert zatca_sale.classify_invoice_subtype("310000000000003", 1000.0) == "standard"
    assert zatca_sale.classify_invoice_subtype("310000000000003", 5000.0) == "standard"
    # B2B below threshold -> simplified (do not route on buyer type alone, ZA-06).
    assert zatca_sale.classify_invoice_subtype("310000000000003", 999.99) == "simplified"
    # B2C (no buyer VAT) at any total -> simplified.
    assert zatca_sale.classify_invoice_subtype("", 5000.0) == "simplified"
    assert zatca_sale.classify_invoice_subtype(None, 5000.0) == "simplified"


async def test_b2b_invoice_is_classified_standard_and_cleared(client, monkeypatch):
    user, token, client_id = await make_client_account(client)
    await _set_vat(client_id)

    doc_id, subtype, xml = await _sign_synthetic(
        client_id, user["id"], buyer_vat="310000000000003", total=2300.0
    )
    # Signed as a standard invoice: UBL subtype marker + buyer VAT in the XML.
    assert subtype == "standard"
    assert zatca_sale.INVOICE_TYPE_NAME_STANDARD in xml
    assert "310000000000003" in xml

    status, clearance_used = await _report_capturing_clearance(client_id, doc_id, monkeypatch)
    assert clearance_used is True
    assert status == "cleared"


async def test_b2c_invoice_is_classified_simplified_and_reported(client, monkeypatch):
    user, token, client_id = await make_client_account(client)
    await _set_vat(client_id)

    doc_id, subtype, xml = await _sign_synthetic(
        client_id, user["id"], buyer_vat=None, total=2300.0
    )
    assert subtype == "simplified"
    assert zatca_sale.INVOICE_TYPE_NAME_SIMPLIFIED in xml

    status, clearance_used = await _report_capturing_clearance(client_id, doc_id, monkeypatch)
    assert clearance_used is False
    assert status == "reported"


async def test_b2b_below_threshold_is_reported_not_cleared(client, monkeypatch):
    user, token, client_id = await make_client_account(client)
    await _set_vat(client_id)

    # VAT-registered buyer but the supply is under 1,000 SAR -> simplified (ZA-06).
    doc_id, subtype, _xml = await _sign_synthetic(
        client_id, user["id"], buyer_vat="310000000000003", total=500.0
    )
    assert subtype == "simplified"

    status, clearance_used = await _report_capturing_clearance(client_id, doc_id, monkeypatch)
    assert clearance_used is False
    assert status == "reported"
