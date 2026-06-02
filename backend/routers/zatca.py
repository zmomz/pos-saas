"""ZATCA Phase-2 onboarding, signing, and reporting endpoints.

Wires `services/zatca.py` (real EC/ECDSA crypto + Fatoora API client) and the
`zatca_credentials` / `zatca_documents` tables into the request flow. This is
the Phase-B replacement for the placeholder HMAC "stamp": invoices are now
signed with a real per-client ECDSA key, archived for the statutory retention
period, and (when the gateway is configured) submitted for reporting/clearance.

Endpoints are client-scoped via the tenancy `clients` row. Gateway calls fail
closed with 503 when ``ZATCA_API_BASE_URL`` / ``ZATCA_ENVIRONMENT`` is unset.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import get_db
from dependencies.auth import get_current_user
from models.clients import Clients
from models.transactions import Transactions
from models.zatca_credentials import ZatcaCredentials
from models.zatca_documents import ZatcaDocuments
from schemas.auth import UserResponse
from services import zatca
from services.production import zatca_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/zatca", tags=["zatca"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class StatusResponse(BaseModel):
    environment: str
    has_csr: bool
    onboarded: bool
    gateway_configured: bool
    pih: Optional[str] = None
    documents: int = 0


class CSRRequest(BaseModel):
    egs_serial: Optional[str] = None
    invoice_type: str = "1100"
    location_address: str = "Riyadh"
    business_category: str = "retail"


class CSRResponse(BaseModel):
    csr_pem: str
    csr_base64: str
    public_key_pem: str


class ComplianceRequest(BaseModel):
    otp: str


class OnboardResponse(BaseModel):
    onboarded: bool
    message: str


class SignResponse(BaseModel):
    document_id: int
    invoice_number: str
    invoice_hash: str
    stamp: str
    icv: int
    previous_hash: str
    verified: bool


class DocumentResponse(BaseModel):
    id: int
    invoice_number: str
    icv: Optional[int] = None
    invoice_hash: Optional[str] = None
    status: str
    submitted_at: Optional[datetime] = None
    retention_until: Optional[datetime] = None
    created_at: Optional[datetime] = None


class ReportResponse(BaseModel):
    document_id: int
    status: str
    response: dict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _get_client(db: AsyncSession, user_id: str) -> Clients:
    result = await db.execute(select(Clients).where(Clients.user_id == user_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=403, detail="Only clients can use ZATCA features")
    return client


async def _get_or_create_creds(db: AsyncSession, client: Clients) -> ZatcaCredentials:
    result = await db.execute(
        select(ZatcaCredentials).where(ZatcaCredentials.client_id == client.id)
    )
    creds = result.scalar_one_or_none()
    if creds is None:
        creds = ZatcaCredentials(
            client_id=client.id,
            environment=zatca.normalize_environment(None),
            pih=zatca.INITIAL_PIH,
            onboarded=False,
        )
        db.add(creds)
        await db.flush()
    return creds


def _retention_until() -> datetime:
    years = int(getattr(settings, "zatca_retention_years", None) or 6)
    return datetime.now(timezone.utc) + timedelta(days=365 * years)


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------
@router.get("/status", response_model=StatusResponse)
async def zatca_status(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    client = await _get_client(db, str(current_user.id))
    result = await db.execute(
        select(ZatcaCredentials).where(ZatcaCredentials.client_id == client.id)
    )
    creds = result.scalar_one_or_none()
    doc_count = 0
    if creds:
        docs = await db.execute(
            select(ZatcaDocuments).where(ZatcaDocuments.client_id == client.id)
        )
        doc_count = len(docs.scalars().all())
    return StatusResponse(
        environment=zatca.normalize_environment(creds.environment if creds else None),
        has_csr=bool(creds and creds.csr_pem),
        onboarded=bool(creds and creds.onboarded),
        gateway_configured=zatca.resolve_base_url() is not None,
        pih=creds.pih if creds else None,
        documents=doc_count,
    )


# ---------------------------------------------------------------------------
# Onboarding step 1 — generate keypair + CSR
# ---------------------------------------------------------------------------
@router.post("/onboard/csr", response_model=CSRResponse)
async def generate_csr(
    data: CSRRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    client = await _get_client(db, str(current_user.id))
    if not client.vat_number:
        raise HTTPException(
            status_code=400,
            detail="Client has no vat_number; set it before generating a CSR.",
        )

    egs_serial = data.egs_serial or f"1-POS|2-SaaS|3-{client.id:06d}"
    key_pem, csr_pem = zatca.generate_egs_keypair_and_csr(
        common_name=client.business_name or f"client-{client.id}",
        organization_name=client.business_name or f"client-{client.id}",
        organization_unit=str(client.id),
        vat_number=client.vat_number,
        egs_serial=egs_serial,
        invoice_type=data.invoice_type,
        location_address=data.location_address,
        business_category=data.business_category,
    )

    creds = await _get_or_create_creds(db, client)
    creds.private_key_enc = zatca.encrypt_secret(key_pem)
    creds.csr_pem = csr_pem
    creds.egs_serial = egs_serial
    if not creds.pih:
        creds.pih = zatca.INITIAL_PIH
    await db.commit()

    return CSRResponse(
        csr_pem=csr_pem,
        csr_base64=zatca.csr_to_base64(csr_pem),
        public_key_pem=zatca.public_key_pem_from_private(key_pem),
    )


# ---------------------------------------------------------------------------
# Onboarding step 2 — compliance CSID (CSR + OTP -> binarySecurityToken)
# ---------------------------------------------------------------------------
@router.post("/onboard/compliance-csid", response_model=OnboardResponse)
async def compliance_csid(
    data: ComplianceRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    client = await _get_client(db, str(current_user.id))
    creds = await _get_or_create_creds(db, client)
    if not creds.csr_pem:
        raise HTTPException(status_code=400, detail="Generate a CSR first (POST /onboard/csr).")

    try:
        api = zatca.ZatcaApiClient.from_settings(creds.environment)
        result = await api.request_compliance_csid(creds.csr_pem, data.otp)
    except zatca.ZatcaApiError as exc:
        raise _api_error(exc)

    creds.compliance_request_id = str(result.get("requestID") or result.get("request_id") or "")
    creds.compliance_csid = result.get("binarySecurityToken")
    secret = result.get("secret")
    if secret:
        creds.compliance_secret_enc = zatca.encrypt_secret(secret)
    await db.commit()
    return OnboardResponse(onboarded=False, message="Compliance CSID stored.")


# ---------------------------------------------------------------------------
# Onboarding step 3 — production CSID
# ---------------------------------------------------------------------------
@router.post("/onboard/production-csid", response_model=OnboardResponse)
async def production_csid(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    client = await _get_client(db, str(current_user.id))
    creds = await _get_or_create_creds(db, client)
    if not (creds.compliance_csid and creds.compliance_secret_enc and creds.compliance_request_id):
        raise HTTPException(status_code=400, detail="Obtain a compliance CSID first.")

    try:
        api = zatca.ZatcaApiClient.from_settings(creds.environment)
        result = await api.request_production_csid(
            creds.compliance_request_id,
            creds.compliance_csid,
            zatca.decrypt_secret(creds.compliance_secret_enc),
        )
    except zatca.ZatcaApiError as exc:
        raise _api_error(exc)

    creds.production_csid = result.get("binarySecurityToken")
    secret = result.get("secret")
    if secret:
        creds.production_secret_enc = zatca.encrypt_secret(secret)
    creds.onboarded = True
    await db.commit()
    return OnboardResponse(onboarded=True, message="Production CSID stored. Onboarding complete.")


# ---------------------------------------------------------------------------
# Sign a transaction's invoice (real ECDSA stamp + retention)
# ---------------------------------------------------------------------------
@router.post("/invoices/{transaction_id}/sign", response_model=SignResponse)
async def sign_invoice(
    transaction_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    client = await _get_client(db, str(current_user.id))
    creds = await _get_or_create_creds(db, client)
    if not creds.private_key_enc:
        raise HTTPException(
            status_code=400,
            detail="No signing key. Run POST /onboard/csr to generate one first.",
        )

    result = await db.execute(
        select(Transactions).where(
            Transactions.id == transaction_id,
            Transactions.client_id == client.id,
        )
    )
    txn = result.scalar_one_or_none()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    # Reuse the existing UBL builder, then hash + sign with real crypto.
    items = json.loads(txn.items_json) if txn.items_json else []
    issued = txn.created_at or datetime.now(timezone.utc)
    xml = zatca_service.generate_xml_invoice(
        seller_name=client.business_name or "Business",
        seller_vat=client.vat_number or "000000000000000",
        buyer_name=txn.customer_name or "عميل",
        buyer_vat="",
        invoice_number=txn.invoice_number,
        issue_date=issued.strftime("%Y-%m-%d"),
        issue_time=issued.strftime("%H:%M:%S"),
        line_items=items,
        total_excluding_vat=txn.subtotal or 0,
        total_vat=txn.vat_amount or 0,
        total_including_vat=txn.total_amount or 0,
    )

    previous_hash = creds.pih or zatca.INITIAL_PIH
    inv_hash = zatca.invoice_hash_b64(xml.encode("utf-8"))
    key_pem = zatca.decrypt_secret(creds.private_key_enc)
    stamp = zatca.sign_invoice_hash(key_pem, inv_hash)
    verified = zatca.verify_stamp(
        zatca.public_key_pem_from_private(key_pem), inv_hash, stamp
    )

    icv = (txn.id or 0)
    doc = ZatcaDocuments(
        client_id=client.id,
        transaction_id=txn.id,
        invoice_number=txn.invoice_number,
        icv=icv,
        invoice_hash=inv_hash,
        previous_hash=previous_hash,
        stamp=stamp,
        signed_xml=xml,
        status="signed",
        retention_until=_retention_until(),
    )
    db.add(doc)

    # Advance the per-client hash chain and persist the real hash on the txn.
    creds.pih = inv_hash
    txn.zatca_hash = inv_hash
    await db.commit()
    await db.refresh(doc)

    return SignResponse(
        document_id=doc.id,
        invoice_number=txn.invoice_number,
        invoice_hash=inv_hash,
        stamp=stamp,
        icv=icv,
        previous_hash=previous_hash,
        verified=verified,
    )


# ---------------------------------------------------------------------------
# Report / clear a signed invoice to the Fatoora gateway
# ---------------------------------------------------------------------------
@router.post("/invoices/{document_id}/report", response_model=ReportResponse)
async def report_invoice(
    document_id: int,
    clearance: bool = Query(False, description="Use clearance (standard invoices) vs reporting (simplified)"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    client = await _get_client(db, str(current_user.id))
    creds = await _get_or_create_creds(db, client)
    if not (creds.onboarded and creds.production_csid and creds.production_secret_enc):
        raise HTTPException(status_code=400, detail="Complete production onboarding first.")

    result = await db.execute(
        select(ZatcaDocuments).where(
            ZatcaDocuments.id == document_id,
            ZatcaDocuments.client_id == client.id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        api = zatca.ZatcaApiClient.from_settings(creds.environment)
        response = await api.submit_invoice(
            signed_xml=doc.signed_xml or "",
            invoice_hash=doc.invoice_hash or "",
            invoice_uuid=doc.invoice_uuid or "",
            token=creds.production_csid,
            secret=zatca.decrypt_secret(creds.production_secret_enc),
            clearance=clearance,
        )
    except zatca.ZatcaApiError as exc:
        doc.status = "failed"
        doc.zatca_response = str(exc)
        await db.commit()
        raise _api_error(exc)

    doc.status = "cleared" if clearance else "reported"
    doc.zatca_response = json.dumps(response, ensure_ascii=False)[:4000]
    doc.submitted_at = datetime.now(timezone.utc)
    await db.commit()
    return ReportResponse(document_id=doc.id, status=doc.status, response=response)


# ---------------------------------------------------------------------------
# Retained documents
# ---------------------------------------------------------------------------
@router.get("/documents", response_model=List[DocumentResponse])
async def list_documents(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    client = await _get_client(db, str(current_user.id))
    result = await db.execute(
        select(ZatcaDocuments)
        .where(ZatcaDocuments.client_id == client.id)
        .order_by(ZatcaDocuments.id.desc())
    )
    return [
        DocumentResponse(
            id=d.id,
            invoice_number=d.invoice_number,
            icv=d.icv,
            invoice_hash=d.invoice_hash,
            status=d.status,
            submitted_at=d.submitted_at,
            retention_until=d.retention_until,
            created_at=d.created_at,
        )
        for d in result.scalars().all()
    ]


def _api_error(exc: zatca.ZatcaApiError) -> HTTPException:
    code = exc.status_code or status.HTTP_502_BAD_GATEWAY
    if exc.error_type == "not_configured":
        code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HTTPException(status_code=code, detail=str(exc))
