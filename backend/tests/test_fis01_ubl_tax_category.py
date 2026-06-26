"""FIS-01 — the signed UBL must derive ``cbc:Percent`` and the tax category
(S / Z / E) from the *actual* invoice rate, not a hardcoded 'S' / '15.00'.

A zero-rated or exempt sale used to emit a tax block claiming 15 % standard rate
while its amounts said otherwise — an internally-contradictory (and non-compliant)
document. These tests drive the public ``generate_xml_invoice`` interface and
assert the tax category mirrors the money it carries.
"""
import uuid
import xml.etree.ElementTree as ET

from sqlalchemy import select

from conftest import make_client_account
from core.database import db_manager
from models.clients import Clients
from models.transactions import Transactions
from services import zatca, zatca_sale
from services.production import zatca_service

CAC = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"

_LINE = [{"name": "Cola", "price": 10.0, "quantity": 1}]


def _tax_category(xml: str):
    """Return ``(category_id, percent)`` from the invoice-level cac:TaxCategory."""
    root = ET.fromstring(xml.encode("utf-8"))
    cat = root.find(f"{{{CAC}}}TaxTotal/{{{CAC}}}TaxSubtotal/{{{CAC}}}TaxCategory")
    assert cat is not None, "TaxCategory missing"
    return cat.findtext(f"{{{CBC}}}ID"), cat.findtext(f"{{{CBC}}}Percent")


def _build(excl, vat, *, tax_category_id=None):
    kwargs = dict(
        seller_name="Acme",
        seller_vat="300000000000003",
        buyer_name="نقدي",
        buyer_vat="",
        invoice_number="INV-1",
        issue_date="2026-06-26",
        issue_time="12:00:00",
        line_items=_LINE,
        total_excluding_vat=excl,
        total_vat=vat,
        total_including_vat=excl + vat,
    )
    if tax_category_id is not None:
        kwargs["tax_category_id"] = tax_category_id
    return zatca_service.generate_xml_invoice(**kwargs)


def test_standard_rate_percent_is_derived_not_hardcoded():
    # A 5 % effective rate must render 5.00 / 'S' — not the old hardcoded 15.00.
    cat_id, percent = _tax_category(_build(100.0, 5.0))
    assert cat_id == "S"
    assert percent == "5.00"


def test_standard_fifteen_percent_still_renders_S_15():
    cat_id, percent = _tax_category(_build(100.0, 15.0))
    assert cat_id == "S"
    assert percent == "15.00"


def test_zero_rated_sale_renders_Z_zero_percent():
    # No VAT on a positive base => zero-rated, not a contradictory 15 % standard.
    cat_id, percent = _tax_category(_build(100.0, 0.0))
    assert cat_id == "Z"
    assert percent == "0.00"


def test_exempt_supply_renders_E_zero_percent():
    # Exempt cannot be told from zero-rated by amounts alone, so the caller
    # signals it explicitly; percent is forced to 0.00.
    cat_id, percent = _tax_category(_build(100.0, 0.0, tax_category_id="E"))
    assert cat_id == "E"
    assert percent == "0.00"


async def test_zero_rated_sale_end_to_end_ubl_qr_and_hash(client):
    """A real signed zero-rated sale: the UBL tax block, the stamped QR VAT tag,
    and the fiscal hash chain all agree on 0 VAT (AC: percent+category+QR; chain
    intact)."""
    user, _token, client_id = await make_client_account(client)

    async with db_manager.async_session_maker() as db:
        client_row = (
            await db.execute(select(Clients).where(Clients.id == client_id))
        ).scalar_one()
        txn = Transactions(
            user_id=str(user["id"]),
            client_id=client_id,
            invoice_number=f"INV-{uuid.uuid4().hex[:10]}",
            subtotal=100.0,
            vat_amount=0.0,  # zero-rated supply
            total_amount=100.0,
            payment_method="cash",
            items_json="[]",
        )
        db.add(txn)
        await db.flush()
        doc, stamped_qr = await zatca_sale.sign_transaction(db, client_row, txn)
        signed_xml = doc.signed_xml
        invoice_hash = doc.invoice_hash
        await db.commit()

    # UBL: derived as zero-rated, not the old hardcoded standard 15 %.
    cat_id, percent = _tax_category(signed_xml)
    assert cat_id == "Z"
    assert percent == "0.00"

    # QR carries the same VAT figure (tag 5) — 0.00.
    tags = zatca.parse_tlv_tags(stamped_qr)
    assert tags[5].decode() == "0.00"

    # Hash chain intact: the stored hash is the digest of the C14N invoice
    # with the signature stripped. Re-register the invoice's own prefixes so the
    # reserialized document matches the one that was hashed (C14N keeps prefixes).
    UBL = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
    EXT = "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2"
    ET.register_namespace("", UBL)
    ET.register_namespace("cac", CAC)
    ET.register_namespace("cbc", CBC)
    root = ET.fromstring(signed_xml.encode("utf-8"))
    exts = root.find(f"{{{EXT}}}UBLExtensions")
    if exts is not None:
        root.remove(exts)
    recomputed = zatca.invoice_hash_b64(
        zatca.canonicalize_invoice_xml(ET.tostring(root, encoding="unicode"))
    )
    assert recomputed == invoice_hash
