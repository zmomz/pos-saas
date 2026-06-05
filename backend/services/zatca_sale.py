"""ZATCA signing on the real sale path + asynchronous Fatoora reporting.

Phase A/B left signing as a *manual* endpoint (`POST /zatca/invoices/{id}/sign`)
sitting **off** the sale path — gap C-3: real cryptography that no real sale ever
exercised. This module closes that gap. ``sign_transaction`` is invoked inside
the atomic POS sale transaction so every completed sale (and every refund credit
note) is hashed, ECDSA-stamped, hash-chained and archived to ``zatca_documents``
before the sale commits. A signing failure rolls the sale back rather than
silently persisting an unsigned fiscal record.

Reporting to the Fatoora gateway is decoupled (``report_document`` /
``report_document_background``): it runs after commit via FastAPI
``BackgroundTasks``, retries transient 5xx, and **fails closed to "pending"**
when the gateway/onboarding is not configured — it never blocks or fails a sale.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from sqlalchemy import func, select

from core.config import settings
from core.database import db_manager
from models.clients import Clients
from models.transactions import Transactions
from models.zatca_credentials import ZatcaCredentials
from models.zatca_documents import ZatcaDocuments
from services import zatca
from services.production import zatca_service

logger = logging.getLogger(__name__)


def _retention_until() -> datetime:
    years = int(getattr(settings, "zatca_retention_years", None) or 6)
    return datetime.now(timezone.utc) + timedelta(days=365 * years)


# ---------------------------------------------------------------------------
# ZA-06 — B2B clearance vs B2C reporting routing
# ---------------------------------------------------------------------------
# A *standard* (B2B) tax invoice must be **cleared** by Fatoora in real time; a
# *simplified* (B2C) invoice is **reported** within 24h via the background job.
# Routing is by invoice *type*, never buyer type alone: a B2B supply below the
# clearance threshold may still be issued as simplified (ZA-06). We classify as
# standard only when the buyer carries a VAT number AND the invoice total is at
# or above the threshold.
B2B_CLEARANCE_THRESHOLD_SAR = float(
    getattr(settings, "zatca_clearance_threshold_sar", None) or 1000.0
)
# UBL ``cbc:InvoiceTypeCode/@name`` subtype markers (ZATCA Phase 2).
INVOICE_TYPE_NAME_STANDARD = "0100000"
INVOICE_TYPE_NAME_SIMPLIFIED = "0200000"


def classify_invoice_subtype(buyer_vat: Optional[str], total: float) -> str:
    """Return ``"standard"`` (B2B → clearance) or ``"simplified"`` (B2C → reporting).

    Per ZA-06 a standard invoice — cleared in real time — requires a VAT-registered
    buyer **and** a total at or above ``B2B_CLEARANCE_THRESHOLD_SAR`` (1,000 SAR by
    default). Everything else — B2C sales, and B2B supplies below the threshold —
    is simplified and reported within 24h. Never routes on buyer type alone.
    """
    has_buyer_vat = bool(buyer_vat and str(buyer_vat).strip())
    if has_buyer_vat and abs(total or 0) >= B2B_CLEARANCE_THRESHOLD_SAR:
        return "standard"
    return "simplified"


def is_zatca_enabled(client: Clients) -> bool:
    """ZA-09: honor the per-client ``zatca_enabled`` opt-out on the sale path.

    ZATCA e-invoicing is the Saudi default — provisioning enables it and the
    column defaults ON — but a non-VAT-registered merchant may switch it off via
    the agent UI. When it is off, a sale (or refund credit note) completes as a
    simplified non-tax receipt: **no** ECDSA stamp/QR, **no** ``zatca_documents``
    row, and nothing queued to Fatoora. Only an **explicit** ``False`` disables;
    a NULL — a legacy client created before the flag was honored, which was
    de-facto always-signed — is treated as enabled so existing behavior holds.
    """
    return getattr(client, "zatca_enabled", None) is not False


async def get_or_create_signing_creds(db, client: Clients) -> ZatcaCredentials:
    """Return the client's ZATCA credentials, self-provisioning a signing key.

    A freshly provisioned client has no EGS key yet (full Fatoora onboarding is a
    separate, operator-driven flow). So every sale can still be signed locally,
    we auto-generate a per-client EC keypair + CSR on first use. The CSR is kept
    so the operator can complete onboarding (compliance/production CSID) later
    without regenerating the key — which would break the existing hash chain.
    """
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

    if not creds.private_key_enc:
        egs_serial = creds.egs_serial or f"1-POS|2-SaaS|3-{client.id:06d}"
        key_pem, csr_pem = zatca.generate_egs_keypair_and_csr(
            common_name=client.business_name or f"client-{client.id}",
            organization_name=client.business_name or f"client-{client.id}",
            organization_unit=str(client.id),
            vat_number=client.vat_number or "300000000000003",
            egs_serial=egs_serial,
            environment=creds.environment,
        )
        creds.private_key_enc = zatca.encrypt_secret(key_pem)
        creds.csr_pem = csr_pem
        creds.egs_serial = egs_serial
        if not creds.pih:
            creds.pih = zatca.INITIAL_PIH
        await db.flush()
    return creds


async def _next_icv(db, client_id: int) -> int:
    """Next Invoice Counter Value for the client's hash chain (1-based)."""
    result = await db.execute(
        select(func.coalesce(func.max(ZatcaDocuments.icv), 0)).where(
            ZatcaDocuments.client_id == client_id
        )
    )
    return int(result.scalar() or 0) + 1


async def sign_transaction(
    db,
    client: Clients,
    txn: Transactions,
    *,
    document_type: str = "invoice",
    invoice_type_code: str = "388",
    billing_reference: Optional[str] = None,
    buyer_vat: Optional[str] = None,
) -> Tuple[ZatcaDocuments, str]:
    """Sign ``txn`` in-place and archive a ``ZatcaDocuments`` row.

    Builds the UBL invoice, computes the canonical hash, produces a **real**
    ECDSA stamp, advances the per-client PIH chain, writes the stamped QR TLV +
    its PNG onto the transaction, and returns ``(document, stamped_qr_tlv)``.
    Runs inside the caller's transaction (no commit) so it is atomic with the
    sale. For a credit note (POS-07) pass ``invoice_type_code="381"`` and
    ``billing_reference`` set to the original invoice number.

    ``buyer_vat`` drives the ZA-06 clearance/reporting routing: when the buyer is
    VAT-registered and the total clears the threshold, the document is classified
    ``standard`` (UBL subtype ``0100000``) and the reporting job clears it in real
    time; otherwise it is ``simplified`` (``0200000``) and reported within 24h.
    The buyer VAT itself is captured/rendered into the UBL buyer block by F-018;
    here it only selects the routing.
    """
    creds = await get_or_create_signing_creds(db, client)

    try:
        line_items: List[dict] = json.loads(txn.items_json) if txn.items_json else []
    except (ValueError, TypeError):
        line_items = []

    issued = txn.created_at or datetime.now(timezone.utc)
    seller_name = client.business_name or "Business"
    seller_vat = client.vat_number or "300000000000003"

    # Credit notes carry positive ZATCA amounts; the transaction row itself may
    # store negatives so reports net out (see routers/pos.py::refund_transaction).
    sub = abs(txn.subtotal or 0)
    vat = abs(txn.vat_amount or 0)
    total = abs(txn.total_amount or 0)

    # ZA-06: route standard (B2B clearance) vs simplified (B2C reporting) by the
    # buyer VAT + total, and mark the UBL subtype accordingly so the document is
    # internally consistent with how the reporting job will submit it.
    invoice_subtype = classify_invoice_subtype(buyer_vat, total)
    invoice_type_name = (
        INVOICE_TYPE_NAME_STANDARD
        if invoice_subtype == "standard"
        else INVOICE_TYPE_NAME_SIMPLIFIED
    )

    xml = zatca_service.generate_xml_invoice(
        seller_name=seller_name,
        seller_vat=seller_vat,
        buyer_name=txn.customer_name or "نقدي",
        buyer_vat=buyer_vat or "",
        invoice_number=txn.invoice_number,
        issue_date=issued.strftime("%Y-%m-%d"),
        issue_time=issued.strftime("%H:%M:%S"),
        line_items=line_items,
        total_excluding_vat=sub,
        total_vat=vat,
        total_including_vat=total,
        invoice_type_code=invoice_type_code,
        invoice_type_name=invoice_type_name,
        billing_reference_id=billing_reference,
    )

    previous_hash = creds.pih or zatca.INITIAL_PIH
    inv_hash = zatca.invoice_hash_b64(xml.encode("utf-8"))
    key_pem = zatca.decrypt_secret(creds.private_key_enc)
    stamp = zatca.sign_invoice_hash(key_pem, inv_hash)

    stamped_qr = zatca.build_stamped_qr_tlv(
        seller_name=seller_name,
        vat_number=seller_vat,
        timestamp=issued.isoformat(),
        total_with_vat=f"{total:.2f}",
        vat_amount=f"{vat:.2f}",
        invoice_hash_b64=inv_hash,
        stamp_b64=stamp,
        public_key_der_base64=zatca.public_key_der_b64(key_pem),
    )

    icv = await _next_icv(db, client.id)
    doc = ZatcaDocuments(
        client_id=client.id,
        transaction_id=txn.id,
        invoice_number=txn.invoice_number,
        document_type=document_type,
        invoice_subtype=invoice_subtype,
        icv=icv,
        invoice_hash=inv_hash,
        previous_hash=previous_hash,
        stamp=stamp,
        signed_xml=xml,
        status="signed",
        retention_until=_retention_until(),
    )
    db.add(doc)

    # Advance the hash chain and stamp the transaction with the real fiscal QR.
    creds.pih = inv_hash
    txn.zatca_hash = inv_hash
    txn.zatca_qr = stamped_qr
    await db.flush()
    return doc, stamped_qr


# ---------------------------------------------------------------------------
# Reporting to the Fatoora gateway (decoupled, retrying, fail-closed)
# ---------------------------------------------------------------------------
async def report_document(
    db,
    doc: ZatcaDocuments,
    creds: Optional[ZatcaCredentials],
    *,
    clearance: Optional[bool] = None,
    max_attempts: int = 3,
) -> str:
    """Submit a signed document to Fatoora, with retry on transient 5xx.

    Returns the resulting ``doc.status``. **Fails closed to "pending"** (the sale
    stays valid and signed) when the gateway is unconfigured or onboarding is
    incomplete — reporting can be retried once the operator finishes onboarding.
    On a terminal gateway/4xx error the document is marked "failed".

    ZA-06 routing: when ``clearance`` is left ``None`` it is derived from the
    document's ``invoice_subtype`` — ``standard`` documents are *cleared* in real
    time, ``simplified`` ones are *reported*. Callers may still pass an explicit
    ``clearance`` to override (e.g. the manual operator endpoint).
    """
    if clearance is None:
        clearance = getattr(doc, "invoice_subtype", None) == "standard"

    gateway_ready = (
        creds is not None
        and creds.onboarded
        and creds.production_csid
        and creds.production_secret_enc
        and zatca.resolve_base_url(creds.environment) is not None
    )
    if not gateway_ready:
        doc.status = "pending"
        await db.flush()
        return doc.status

    last_exc: Optional[zatca.ZatcaApiError] = None
    for attempt in range(1, max_attempts + 1):
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
            last_exc = exc
            # Retry only transient server-side failures; 4xx is terminal.
            transient = (exc.status_code or 0) >= 500 or exc.error_type == "network"
            if transient and attempt < max_attempts:
                await asyncio.sleep(0)  # yield; real deployments back off
                continue
            doc.status = "failed"
            doc.zatca_response = str(exc)[:4000]
            await db.flush()
            return doc.status

        doc.status = "cleared" if clearance else "reported"
        doc.zatca_response = json.dumps(response, ensure_ascii=False)[:4000]
        doc.submitted_at = datetime.now(timezone.utc)
        await db.flush()
        return doc.status

    # Loop fell through (all attempts raised transient) — mark failed.
    doc.status = "failed"
    if last_exc is not None:
        doc.zatca_response = str(last_exc)[:4000]
    await db.flush()
    return doc.status


async def report_pending_documents(
    db,
    client_id: int,
    *,
    statuses: Tuple[str, ...] = ("pending", "failed"),
) -> dict:
    """Resubmit every stuck (pending/failed) document for a client to Fatoora.

    The sale-time reporting (``report_document_background``) fires **once** via
    ``BackgroundTasks``. On a default, un-onboarded install it fails closed to
    ``pending`` and is never retried — even after the operator later completes
    onboarding (ZA-06 demands a retrying background job; ZA-08 demands stuck docs
    be reconcilable). This sweep walks the client's pending/failed backlog in
    counter order and resubmits each through the **same** routing as the live
    path (clearance for ``standard``, reporting for ``simplified`` — derived from
    the stored ``invoice_subtype``).

    Idempotent: already-``cleared``/``reported`` documents are not selected, so
    re-running after a successful sweep is a no-op; a still-unconfigured gateway
    simply leaves each document ``pending`` again. Runs inside the caller's
    transaction (no commit) so the whole sweep is atomic with the caller.

    Returns a summary ``{processed, cleared, reported, pending, failed}``.
    """
    creds = (
        await db.execute(
            select(ZatcaCredentials).where(ZatcaCredentials.client_id == client_id)
        )
    ).scalar_one_or_none()

    docs = (
        await db.execute(
            select(ZatcaDocuments)
            .where(
                ZatcaDocuments.client_id == client_id,
                ZatcaDocuments.status.in_(statuses),
            )
            .order_by(ZatcaDocuments.icv.asc(), ZatcaDocuments.id.asc())
        )
    ).scalars().all()

    summary = {"processed": 0, "cleared": 0, "reported": 0, "pending": 0, "failed": 0}
    for doc in docs:
        result_status = await report_document(db, doc, creds)
        summary["processed"] += 1
        if result_status in summary:
            summary[result_status] += 1
    return summary


async def report_document_background(document_id: int, client_id: int) -> None:
    """BackgroundTasks entry point: report one document in its own DB session.

    Never raises — reporting problems must not surface to (or after) the sale.
    """
    try:
        await db_manager.ensure_initialized()
        async with db_manager.async_session_maker() as db:
            doc = (
                await db.execute(
                    select(ZatcaDocuments).where(
                        ZatcaDocuments.id == document_id,
                        ZatcaDocuments.client_id == client_id,
                    )
                )
            ).scalar_one_or_none()
            if doc is None:
                return
            creds = (
                await db.execute(
                    select(ZatcaCredentials).where(
                        ZatcaCredentials.client_id == client_id
                    )
                )
            ).scalar_one_or_none()
            await report_document(db, doc, creds)
            await db.commit()
    except Exception as exc:  # pragma: no cover - background must never crash
        logger.warning("ZATCA background reporting failed for doc %s: %s", document_id, exc)
