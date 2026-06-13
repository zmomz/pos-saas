"""ZATCA Phase-2 tests: real crypto primitives + onboarding/signing/retention.

The cryptography (keypair/CSR, ECDSA stamp, AES-256 secret storage) is exercised
directly. The HTTP flow covers CSR generation, real-signature signing with
hash-chain advance + 6-year retention, and the 503 fail-closed contract for
gateway calls when no Fatoora endpoint is configured.
"""
from sqlalchemy import select

from conftest import add_product, auth_headers, make_client_account
from core.database import db_manager
from models.clients import Clients
from services import zatca


# ---------------------------------------------------------------------------
# Unit: cryptographic primitives (no HTTP, no network)
# ---------------------------------------------------------------------------
def test_keypair_and_csr_are_valid():
    key_pem, csr_pem = zatca.generate_egs_keypair_and_csr(
        common_name="Acme Store",
        organization_name="Acme LLC",
        organization_unit="42",
        vat_number="300000000000003",
        egs_serial="1-POS|2-SaaS|3-000042",
    )
    assert "BEGIN PRIVATE KEY" in key_pem
    assert "BEGIN CERTIFICATE REQUEST" in csr_pem
    assert zatca.is_valid_csr(csr_pem)
    # CSR carries the VAT number and the EGS serial in the SAN directory.
    from cryptography.x509 import load_pem_x509_csr

    csr = load_pem_x509_csr(csr_pem.encode())
    der = csr.public_bytes(__import__("cryptography").hazmat.primitives.serialization.Encoding.DER)
    assert b"300000000000003" in der
    assert b"1-POS" in der


def test_stamp_sign_and_verify_roundtrip():
    key_pem, _ = zatca.generate_egs_keypair_and_csr(
        common_name="A", organization_name="A", organization_unit="1",
        vat_number="300000000000003", egs_serial="1-A|2-B|3-C",
    )
    pub = zatca.public_key_pem_from_private(key_pem)
    h = zatca.invoice_hash_b64(b"<Invoice>real</Invoice>")
    stamp = zatca.sign_invoice_hash(key_pem, h)
    assert zatca.verify_stamp(pub, h, stamp)
    # A different invoice hash must not verify against the same stamp.
    other = zatca.invoice_hash_b64(b"<Invoice>tampered</Invoice>")
    assert not zatca.verify_stamp(pub, other, stamp)


def test_secret_encryption_roundtrip():
    enc = zatca.encrypt_secret("zatca-issued-secret")
    assert enc != "zatca-issued-secret"
    assert zatca.decrypt_secret(enc) == "zatca-issued-secret"


def test_gateway_not_configured_by_default():
    # No ZATCA_API_BASE_URL / ZATCA_ENVIRONMENT in the test env -> not configured.
    assert zatca.resolve_base_url() is None


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------
async def _set_vat(client_id: int, vat: str = "300000000000003"):
    async with db_manager.async_session_maker() as db:
        row = (await db.execute(select(Clients).where(Clients.id == client_id))).scalar_one()
        row.vat_number = vat
        await db.commit()


async def _make_transaction(client, headers, client_id, user_id) -> int:
    pid = await add_product(client_id, user_id, name="Cola", quantity=10, price=10.0)
    resp = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Cola", "price": 10.0, "quantity": 2}],
            "payment_method": "cash",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# HTTP: onboarding + signing
# ---------------------------------------------------------------------------
async def test_csr_requires_vat_number(client):
    _, token, _ = await make_client_account(client)
    resp = await client.post("/api/v1/zatca/onboard/csr", json={}, headers=auth_headers(token))
    assert resp.status_code == 400
    assert "vat_number" in resp.json()["detail"]


async def test_generate_csr_and_status(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _set_vat(client_id)

    resp = await client.post("/api/v1/zatca/onboard/csr", json={}, headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert zatca.is_valid_csr(body["csr_pem"])
    assert body["csr_base64"]

    status = (await client.get("/api/v1/zatca/status", headers=headers)).json()
    assert status["has_csr"] is True
    assert status["onboarded"] is False
    assert status["gateway_configured"] is False
    assert status["pih"] == zatca.INITIAL_PIH


async def test_sign_invoice_produces_verifiable_stamp_and_retention(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _set_vat(client_id)
    await client.post("/api/v1/zatca/onboard/csr", json={}, headers=headers)
    txn_id = await _make_transaction(client, headers, client_id, user["id"])

    resp = await client.post(f"/api/v1/zatca/invoices/{txn_id}/sign", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["verified"] is True          # real ECDSA signature, not HMAC
    assert body["previous_hash"] == zatca.INITIAL_PIH
    assert body["invoice_hash"] and body["stamp"]

    # Document is retained with a future retention date (6-year default).
    # Status is "signed" then "pending" once background reporting runs and finds
    # no Fatoora gateway configured (fail-closed, sale stays valid).
    docs = (await client.get("/api/v1/zatca/documents", headers=headers)).json()
    assert docs["total"] == 1
    assert docs["items"][0]["status"] in ("signed", "pending")
    assert docs["items"][0]["retention_until"] is not None

    # Status now reflects the advanced hash chain (PIH != initial).
    status = (await client.get("/api/v1/zatca/status", headers=headers)).json()
    assert status["documents"] == 1
    assert status["pih"] == body["invoice_hash"]
    assert status["pih"] != zatca.INITIAL_PIH


async def test_sign_chains_previous_hash(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _set_vat(client_id)
    await client.post("/api/v1/zatca/onboard/csr", json={}, headers=headers)

    t1 = await _make_transaction(client, headers, client_id, user["id"])
    t2 = await _make_transaction(client, headers, client_id, user["id"])
    s1 = (await client.post(f"/api/v1/zatca/invoices/{t1}/sign", headers=headers)).json()
    s2 = (await client.post(f"/api/v1/zatca/invoices/{t2}/sign", headers=headers)).json()
    # The second invoice chains onto the first invoice's hash.
    assert s2["previous_hash"] == s1["invoice_hash"]


async def test_sale_autosigns_without_manual_onboarding(client):
    """C-3: a sale signs itself (auto-provisioned EGS key) with no manual CSR.

    The signing key no longer has to be created by hand before a sale can be
    signed — the POS path provisions it and signs every invoice. The manual
    ``/sign`` endpoint is therefore idempotent: it returns the already-signed
    document rather than minting a duplicate fiscal record.
    """
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _set_vat(client_id)
    txn_id = await _make_transaction(client, headers, client_id, user["id"])

    # The sale already produced exactly one signed document for this client
    # ("signed", or "pending" after background reporting finds no gateway).
    docs = (await client.get("/api/v1/zatca/documents", headers=headers)).json()
    assert docs["total"] == 1
    assert docs["items"][0]["status"] in ("signed", "pending")

    # Manual sign is idempotent — same document, no duplicate, chain intact.
    resp = await client.post(f"/api/v1/zatca/invoices/{txn_id}/sign", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["document_id"] == docs["items"][0]["id"]
    docs_after = (await client.get("/api/v1/zatca/documents", headers=headers)).json()
    assert docs_after["total"] == 1


async def test_report_fails_closed_without_onboarding(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _set_vat(client_id)
    await client.post("/api/v1/zatca/onboard/csr", json={}, headers=headers)
    txn_id = await _make_transaction(client, headers, client_id, user["id"])
    sign = (await client.post(f"/api/v1/zatca/invoices/{txn_id}/sign", headers=headers)).json()
    # Not onboarded to production yet -> 400 (must complete onboarding first).
    resp = await client.post(
        f"/api/v1/zatca/invoices/{sign['document_id']}/report", headers=headers
    )
    assert resp.status_code == 400


async def test_compliance_csid_503_when_gateway_unconfigured(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    await _set_vat(client_id)
    await client.post("/api/v1/zatca/onboard/csr", json={}, headers=headers)
    # CSR exists, but no Fatoora gateway configured -> 503, not a crash/hang.
    resp = await client.post(
        "/api/v1/zatca/onboard/compliance-csid",
        json={"otp": "123456"},
        headers=headers,
    )
    assert resp.status_code == 503


async def test_non_client_cannot_access(client):
    from conftest import register_user

    _, token, _ = await register_user(client)  # plain user, no client row
    resp = await client.get("/api/v1/zatca/status", headers=auth_headers(token))
    assert resp.status_code == 403
