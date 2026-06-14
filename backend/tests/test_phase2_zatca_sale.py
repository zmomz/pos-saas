"""Phase 2 — ZATCA compliance on the real sale path (C-3, C-4, POS-07, ZA-04).

Proves that every POS sale is signed/stamped/chained, that the fiscal QR is a
real stamped TLV rendered to a PNG, that refunds issue compliant 381 credit
notes (restoring stock + chaining), that Fatoora reporting retries transient
failures and fails closed when unconfigured, and that the chain+signature
integrity endpoint validates the whole chain.
"""
import base64
import re
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
                "invoice_uuid": d.invoice_uuid,
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


async def test_sale_produces_signed_ubl_with_uuid_and_c14n_hash(client):
    """C2 / ISSUE-015: a completed sale archives a gateway-valid document — the
    signed XML carries an enveloped ds:Signature in UBLExtensions, the persisted
    invoice_uuid equals the document's cbc:UUID, and the invoice hash is taken
    over the C14N invoice (not the raw string)."""
    import xml.etree.ElementTree as ET

    from services import zatca

    DS = "http://www.w3.org/2000/09/xmldsig#"
    EXT = "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2"
    UBL = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
    CAC = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
    CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
    # Reserialize with the invoice's own prefixes so removing the signature
    # reconstructs the original document (C14N preserves prefixes).
    ET.register_namespace("", UBL)
    ET.register_namespace("cac", CAC)
    ET.register_namespace("cbc", CBC)

    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _set_vat(client_id)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=10, price=10.0)
    await _sale(client, headers, pid)

    doc = (await _docs(client_id))[0]
    signed = doc["signed_xml"]

    # AC1: the submitted document is the signed UBL, not the plain one.
    root = ET.fromstring(signed.encode("utf-8"))
    exts = root.find(f"{{{EXT}}}UBLExtensions")
    assert exts is not None
    assert exts.find(f".//{{{DS}}}Signature") is not None
    assert (exts.findtext(f".//{{{DS}}}SignatureValue") or "").strip()

    # AC3: cbc:UUID is non-empty and equals the persisted invoice_uuid.
    uuid_text = root.findtext(f"{{{UBL}}}UUID") or root.findtext(f"{{{CBC}}}UUID")
    assert doc["invoice_uuid"]
    assert uuid_text == doc["invoice_uuid"]

    # AC2: invoice_hash is the digest of the C14N invoice (sans signature).
    root.remove(exts)
    recomputed = zatca.invoice_hash_b64(
        zatca.canonicalize_invoice_xml(ET.tostring(root, encoding="unicode"))
    )
    assert recomputed == doc["invoice_hash"]


def _embedded_pih(signed_xml: str) -> str:
    """The PIH actually embedded in the UBL (cbc:EmbeddedDocumentBinaryObject
    under the ``PIH`` AdditionalDocumentReference) — what a verifier re-reads,
    distinct from the recorded ``ZatcaDocuments.previous_hash``."""
    m = re.search(r"EmbeddedDocumentBinaryObject[^>]*>([^<]*)<", signed_xml)
    assert m, "no embedded PIH found in signed XML"
    return m.group(1)


async def test_pih_chain_does_not_bleed_across_clients(client):
    """C1: interleaving two clients' sales must not let one client's invoice hash
    leak into the other's on-chain PIH. The PIH *embedded in each UBL* must equal
    that client's own recorded chain head — proving no fiscal state lives on the
    process-global ``zatca_service`` singleton."""
    user_a, token_a, cid_a = await make_client_account(client)
    user_b, token_b, cid_b = await make_client_account(client)
    ha, hb = auth_headers(token_a), auth_headers(token_b)
    await _set_vat(cid_a)
    await _set_vat(cid_b)
    pa = await add_product(cid_a, user_a["id"], name="Cola", quantity=50, price=5.0)
    pb = await add_product(cid_b, user_b["id"], name="Pepsi", quantity=50, price=5.0)

    # Interleave the two clients' sales: A1, B1, A2, B2.
    await _sale(client, ha, pa)
    await _sale(client, hb, pb)
    await _sale(client, ha, pa)
    await _sale(client, hb, pb)

    docs_a = await _docs(cid_a)
    docs_b = await _docs(cid_b)
    assert len(docs_a) == 2 and len(docs_b) == 2

    # The PIH embedded in every UBL equals that document's recorded chain head
    # (so a verifier re-reading the XML sees the real per-client chain).
    for docs in (docs_a, docs_b):
        for d in docs:
            assert _embedded_pih(d["signed_xml"]) == d["previous_hash"]

    # Each client's first invoice seeds from INITIAL_PIH; the second chains onto
    # *its own* first invoice — never the other client's, despite interleaving.
    assert _embedded_pih(docs_a[0]["signed_xml"]) == zatca.INITIAL_PIH
    assert _embedded_pih(docs_b[0]["signed_xml"]) == zatca.INITIAL_PIH
    assert _embedded_pih(docs_a[1]["signed_xml"]) == docs_a[0]["invoice_hash"]
    assert _embedded_pih(docs_b[1]["signed_xml"]) == docs_b[0]["invoice_hash"]


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
# POS-07: partial / line-level refunds (F-007)
# ---------------------------------------------------------------------------
async def _txn_status(txn_id: int) -> str:
    async with db_manager.async_session_maker() as db:
        row = (
            await db.execute(select(Transactions).where(Transactions.id == txn_id))
        ).scalar_one()
        return row.status


async def test_partial_refund_credits_one_unit_and_marks_partial_refunded(client):
    """Refund 1 of 3 units → credit note nets one unit (incl. its VAT share),
    stock goes up by exactly 1, and the original lands in ``partial_refunded``."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _set_vat(client_id)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=10, price=10.0)

    sale = await _sale(client, headers, pid, qty=3)         # subtotal 30, VAT 4.5, total 34.5
    assert await get_product_quantity(pid) == 7             # 10 - 3 sold

    resp = await client.post(
        f"/api/v1/pos/transactions/{sale['id']}/refund",
        json={"lines": [{"product_id": pid, "quantity": 1}]},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    refund = resp.json()
    # One of three units → a third of the 34.5 invoice = 11.5 (negative on the note).
    assert refund["total_amount"] == -11.5
    assert refund["original_status"] == "partial_refunded"

    # Only the returned unit is restored.
    assert await get_product_quantity(pid) == 8
    # The original invoice reflects the partial state for the next refund.
    assert await _txn_status(sale["id"]) == "partial_refunded"


async def test_successive_partial_refunds_complete_to_refunded(client):
    """Two partial refunds that together return every unit flip the original to
    ``refunded`` and the second cannot over-refund the remaining balance."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _set_vat(client_id)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=10, price=10.0)

    sale = await _sale(client, headers, pid, qty=3)

    r1 = await client.post(
        f"/api/v1/pos/transactions/{sale['id']}/refund",
        json={"lines": [{"product_id": pid, "quantity": 1}]},
        headers=headers,
    )
    assert r1.status_code == 200
    assert r1.json()["original_status"] == "partial_refunded"

    # Returning the remaining 2 units completes the refund.
    r2 = await client.post(
        f"/api/v1/pos/transactions/{sale['id']}/refund",
        json={"lines": [{"product_id": pid, "quantity": 2}]},
        headers=headers,
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["original_status"] == "refunded"
    assert await get_product_quantity(pid) == 10            # all stock restored
    assert await _txn_status(sale["id"]) == "refunded"

    # A third refund has nothing left to return.
    r3 = await client.post(
        f"/api/v1/pos/transactions/{sale['id']}/refund", headers=headers
    )
    assert r3.status_code == 400
    assert "already refunded" in r3.json()["detail"].lower()


async def test_partial_refund_rejects_over_quantity(client):
    """Asking to return more units than were sold (net of prior refunds) is a 400
    and restores nothing."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _set_vat(client_id)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=10, price=10.0)

    sale = await _sale(client, headers, pid, qty=2)

    resp = await client.post(
        f"/api/v1/pos/transactions/{sale['id']}/refund",
        json={"lines": [{"product_id": pid, "quantity": 3}]},   # only 2 were sold
        headers=headers,
    )
    assert resp.status_code == 400
    assert "exceeds" in resp.json()["detail"].lower()
    # Nothing changed: stock still reflects the 2 sold, original still completed.
    assert await get_product_quantity(pid) == 8
    assert await _txn_status(sale["id"]) == "completed"


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
    # Live submission is gated off by default (ISSUE-016) — enable it for this test.
    monkeypatch.setattr(zatca_sale.settings, "zatca_live_submission_enabled", True)
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

    # Live submission is gated off by default (ISSUE-016) — enable it for this test.
    monkeypatch.setattr(zatca_sale.settings, "zatca_live_submission_enabled", True)
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


# ---------------------------------------------------------------------------
# F-018 (CRM-01 / ZA-06): buyer VAT captured on the sale path + rendered into
# the invoice buyer block, making a B2B standard invoice actually possible.
# ---------------------------------------------------------------------------
async def _txn_buyer_vat(txn_id: int):
    async with db_manager.async_session_maker() as db:
        return (
            await db.execute(
                select(Transactions.customer_vat_number).where(Transactions.id == txn_id)
            )
        ).scalar_one()


async def test_b2b_sale_captures_buyer_vat_into_xml_and_invoice(client):
    """A sale with an explicit buyer VAT ≥ threshold yields a standard invoice
    whose UBL carries the buyer CompanyID, and the HTML/PDF printables show it."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _set_vat(client_id)
    pid = await add_product(client_id, user["id"], name="Bulk", quantity=10, price=1000.0)

    resp = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Bulk", "price": 1000.0, "quantity": 1}],
            "payment_method": "cash",
            "customer_name": "Acme LLC",
            "customer_vat_number": "310000000000003",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    txn_id = body["id"]

    # The buyer VAT is persisted on the transaction (F-018).
    assert await _txn_buyer_vat(txn_id) == "310000000000003"

    # The signed UBL carries the buyer tax block + the standard subtype marker (ZA-06).
    docs = await _docs(client_id)
    assert len(docs) == 1
    xml = docs[0]["signed_xml"]
    assert "AccountingCustomerParty" in xml
    assert "310000000000003" in xml
    assert zatca_sale.INVOICE_TYPE_NAME_STANDARD in xml

    # The always-Arabic HTML invoice (printable) renders the buyer VAT.
    html_resp = await client.get(
        f"/api/v1/pos/transactions/{txn_id}/invoice", headers=headers
    )
    assert html_resp.status_code == 200
    assert "310000000000003" in html_resp.text

    # The A4 PDF endpoint returns real PDF bytes for the same invoice.
    pdf_resp = await client.get(
        f"/api/v1/pos/transactions/{txn_id}/pdf", headers=headers
    )
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"
    assert pdf_resp.content[:4] == b"%PDF"


async def test_buyer_vat_resolved_from_saved_customer_record(client):
    """A sale tagged only with customer_id inherits that customer's saved VAT,
    so a B2B sale clears without the cashier re-typing the number (CRM-01)."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _set_vat(client_id)
    pid = await add_product(client_id, user["id"], name="Bulk", quantity=10, price=1000.0)

    # Create a B2B customer carrying a VAT number via the entity triad.
    cust_resp = await client.post(
        "/api/v1/entities/customers",
        json={"name": "Acme LLC", "vat_number": "311111111111113"},
        headers=headers,
    )
    assert cust_resp.status_code == 201, cust_resp.text
    customer_id = cust_resp.json()["id"]

    resp = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Bulk", "price": 1000.0, "quantity": 1}],
            "payment_method": "cash",
            "customer_id": customer_id,
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    txn_id = resp.json()["id"]

    # The buyer VAT was resolved from the saved customer and stamped on the sale.
    assert await _txn_buyer_vat(txn_id) == "311111111111113"
    xml = (await _docs(client_id))[0]["signed_xml"]
    assert "311111111111113" in xml
    assert zatca_sale.INVOICE_TYPE_NAME_STANDARD in xml


async def test_b2c_sale_has_no_buyer_vat_block(client):
    """An ordinary B2C sale captures no buyer VAT and emits no buyer tax block."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _set_vat(client_id)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=10, price=1000.0)

    body = await _sale(client, headers, pid, name="Cola", price=1000.0, qty=1)
    assert await _txn_buyer_vat(body["id"]) is None
    xml = (await _docs(client_id))[0]["signed_xml"]
    # The UBL buyer PartyTaxScheme is only emitted when a buyer VAT is present.
    assert "PartyTaxScheme" in xml  # seller block always present
    assert "AccountingCustomerParty" in xml
    # No buyer CompanyID: the customer party carries a name only.
    cust_block = xml.split("AccountingCustomerParty", 1)[1]
    assert "CompanyID" not in cust_block.split("PaymentMeans", 1)[0]


def test_pdf_buyer_block_renders_vat_when_present(monkeypatch):
    """Unit: the buyer VAT is threaded into the A4 PDF buyer block when present
    and omitted otherwise. fpdf2 zlib-compresses content streams, so we assert the
    extra buyer-VAT line enlarges the document rather than grepping raw bytes; the
    visible-text rendering is covered by the always-Arabic HTML printable test."""
    from services import pdf_render

    # Force the deterministic Latin-1 fallback so the comparison is stable across
    # environments regardless of whether the Arabic font/shapers are installed.
    monkeypatch.setattr(pdf_render, "_arabic_available", lambda: False)
    common = dict(
        seller_name="Seller",
        seller_vat="300000000000003",
        buyer_name="Acme LLC",
        invoice_number="INV-0001-000001",
        issue_date="2026-06-03",
        line_items=[{"name": "Bulk", "quantity": 1, "price": 1000.0}],
        subtotal=1000.0,
        discount=0.0,
        vat_amount=150.0,
        total_amount=1150.0,
    )
    with_vat = pdf_render.invoice_pdf_bytes(buyer_vat="310000000000003", **common)
    without_vat = pdf_render.invoice_pdf_bytes(buyer_vat="", **common)

    assert with_vat[:4] == b"%PDF" and without_vat[:4] == b"%PDF"
    # The buyer-VAT line is rendered only in the first document.
    assert len(with_vat) > len(without_vat)


# ---------------------------------------------------------------------------
# F-020 (ZA-06 retry / ZA-08): reconcile sweep resubmits stuck pending/failed
# documents once the client is onboarded — fail-closed is no longer a dead end.
# ---------------------------------------------------------------------------
def _mock_accepting_gateway(monkeypatch):
    """Patch ZATCA to a configured Fatoora that accepts every submission."""
    # Live submission is gated off by default (ISSUE-016) — enable it for the sweep.
    monkeypatch.setattr(zatca_sale.settings, "zatca_live_submission_enabled", True)
    monkeypatch.setattr(zatca, "resolve_base_url", lambda environment=None: "http://mock-fatoora")

    class _FakeApi:
        async def submit_invoice(self, **kwargs):
            return {"reportingStatus": "REPORTED"}

    monkeypatch.setattr(
        zatca.ZatcaApiClient, "from_settings",
        classmethod(lambda cls, environment=None: _FakeApi()),
    )


async def _force_stuck_and_onboard(client_id: int, statuses):
    """Set each of the client's documents to a stuck status, then onboard.

    Returns nothing; leaves the gateway creds onboarded so a sweep can submit.
    """
    async with db_manager.async_session_maker() as db:
        docs = (
            await db.execute(
                select(ZatcaDocuments)
                .where(ZatcaDocuments.client_id == client_id)
                .order_by(ZatcaDocuments.icv.asc())
            )
        ).scalars().all()
        for doc, st in zip(docs, statuses):
            doc.status = st
        creds = (
            await db.execute(select(ZatcaCredentials).where(ZatcaCredentials.client_id == client_id))
        ).scalar_one()
        creds.onboarded = True
        creds.production_csid = "csid-token"
        creds.production_secret_enc = zatca.encrypt_secret("prod-secret")
        await db.commit()


async def test_report_pending_sweep_resubmits_stuck_documents(client, monkeypatch):
    """A default install leaves docs stuck at pending/failed; after onboarding the
    sweep resubmits the whole backlog and flips them to reported (ZA-06/ZA-08)."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _set_vat(client_id)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=50, price=1000.0)

    # Two B2C sales while the gateway is unconfigured -> documents fail closed.
    await _sale(client, headers, pid, price=1000.0, qty=1)
    await _sale(client, headers, pid, price=1000.0, qty=1)

    # Force the stuck states deterministically (one pending, one failed), independent
    # of background-task timing, then complete onboarding.
    await _force_stuck_and_onboard(client_id, ["pending", "failed"])

    _mock_accepting_gateway(monkeypatch)

    resp = await client.post("/api/v1/zatca/documents/report-pending", headers=headers)
    assert resp.status_code == 200, resp.text
    summary = resp.json()
    assert summary["processed"] == 2
    assert summary["reported"] == 2          # both B2C simplified -> reported
    assert summary["pending"] == 0 and summary["failed"] == 0

    # Persisted: no document remains stuck.
    docs = await _docs(client_id)
    assert [d["status"] for d in docs] == ["reported", "reported"]

    # Idempotent: a second sweep has nothing to do.
    again = await client.post("/api/v1/zatca/documents/report-pending", headers=headers)
    assert again.status_code == 200
    assert again.json()["processed"] == 0


async def test_report_pending_clears_standard_b2b_documents(client, monkeypatch):
    """A stuck *standard* (B2B) document is *cleared* by the sweep, not merely
    reported — the sweep preserves the ZA-06 clearance/reporting routing."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _set_vat(client_id)

    # Sign a standard (B2B, >= 1,000 SAR) invoice directly; it lands signed.
    doc_id, subtype, _xml = await _sign_synthetic(
        client_id, user["id"], buyer_vat="310000000000003", total=2300.0
    )
    assert subtype == "standard"

    await _force_stuck_and_onboard(client_id, ["pending"])
    _mock_accepting_gateway(monkeypatch)

    resp = await client.post("/api/v1/zatca/documents/report-pending", headers=headers)
    assert resp.status_code == 200, resp.text
    summary = resp.json()
    assert summary["processed"] == 1
    assert summary["cleared"] == 1 and summary["reported"] == 0

    docs = await _docs(client_id)
    assert docs[0]["status"] == "cleared"


async def test_report_pending_requires_onboarding(client):
    """The sweep refuses with a clear 400 until production onboarding is done."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _set_vat(client_id)
    pid = await add_product(client_id, user["id"], name="Cola", quantity=10, price=10.0)
    await _sale(client, headers, pid)

    resp = await client.post("/api/v1/zatca/documents/report-pending", headers=headers)
    assert resp.status_code == 400
    assert "onboarding" in resp.json()["detail"].lower()
