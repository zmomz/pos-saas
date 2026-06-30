"""
Production services module for the multi-tenant POS system.
Contains rate limiting, performance monitoring, ZATCA Phase 2,
PDF invoice generation, email, webhooks, low stock alerts,
bulk import/export, search, analytics, and offline sync services.
"""

import base64
import csv
import functools
import hashlib
import hmac
import io
import json
import logging
import os
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from xml.etree.ElementTree import Element, SubElement, tostring

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.formatting import format_money_ar, to_arabic_digits
from core.money import quantize_money, to_decimal
from services.zatca import INITIAL_PIH

logger = logging.getLogger(__name__)

# ZATCA tax category identifiers (UN/CEFACT 5305 subset ZATCA accepts).
TAX_CATEGORY_STANDARD = "S"  # Standard rate (e.g. 15 %)
TAX_CATEGORY_ZERO = "Z"  # Zero-rated supply (0 %)
TAX_CATEGORY_EXEMPT = "E"  # Exempt from VAT (0 %)


def derive_tax_category(
    taxable_amount: float,
    vat_amount: float,
    *,
    category_id: Optional[str] = None,
) -> tuple[str, str]:
    """Derive ``(category_id, percent)`` for the UBL ``cac:TaxCategory`` from the
    invoice's actual money — never a hardcoded 'S' / '15.00'.

    The effective percent is ``vat / taxable * 100`` computed in exact Decimal and
    quantized to 2dp, so the rendered ``cbc:Percent`` always agrees with the
    amounts. Category:

    - explicit ``category_id`` (e.g. ``'E'`` exempt) wins, since exempt vs
      zero-rated cannot be told apart from the amounts alone (both carry 0 VAT);
    - otherwise ``'S'`` when VAT was charged on the base, else ``'Z'`` (zero-rated).

    A zero-rate category ('Z'/'E') forces percent ``0.00`` regardless of any drift.
    """
    taxable = to_decimal(taxable_amount)
    vat = to_decimal(vat_amount)
    if taxable > 0 and vat > 0:
        percent = quantize_money(vat / taxable * 100)
    else:
        percent = quantize_money(0)

    if category_id:
        cat = category_id
    elif percent > 0:
        cat = TAX_CATEGORY_STANDARD
    else:
        cat = TAX_CATEGORY_ZERO

    # A zero-rated / exempt category never carries a non-zero percent.
    if cat in (TAX_CATEGORY_ZERO, TAX_CATEGORY_EXEMPT):
        percent = quantize_money(0)

    return cat, f"{percent:.2f}"


@functools.lru_cache(maxsize=1)
def _riyal_font_face() -> str:
    """An ``@font-face`` block embedding the Saudi Riyal glyph (U+20C1) inline.

    The always-Arabic HTML documents render in 'Noto Sans Arabic', which has no
    glyph for the new Riyal sign. Embedding the tiny single-glyph webfont as a
    base64 data-URI (scoped to U+20C1 via ``unicode-range``) makes the symbol
    render in any browser or HTML→PDF engine, with every other character falling
    through to the Arabic body font — the document-side analogue of the frontend
    build's index.css trick. Returns ``""`` if the font file is missing.
    """
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "assets",
        "fonts",
        "SaudiRiyal-Regular.woff2",
    )
    try:
        with open(path, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode("ascii")
    except OSError:  # pragma: no cover - font ships with the repo
        return ""
    return (
        "@font-face{font-family:'Saudi Riyal';"
        f"src:url(data:font/woff2;base64,{b64}) format('woff2');"
        "unicode-range:U+20C1;font-display:swap;}"
    )


# =============================================================================
# Rate Limiter (In-Memory Token Bucket)
# =============================================================================
class RateLimiter:
    """In-memory token bucket rate limiter per user."""

    def __init__(self, max_tokens: int = 100, refill_rate: float = 10.0):
        """
        Args:
            max_tokens: Maximum tokens per user bucket.
            refill_rate: Tokens added per second.
        """
        self.max_tokens = max_tokens
        self.refill_rate = refill_rate
        self._buckets: Dict[str, Dict[str, float]] = {}

    def _get_bucket(self, user_id: str) -> Dict[str, float]:
        now = time.time()
        if user_id not in self._buckets:
            self._buckets[user_id] = {
                "tokens": float(self.max_tokens),
                "last_refill": now,
            }
        bucket = self._buckets[user_id]
        elapsed = now - bucket["last_refill"]
        bucket["tokens"] = min(
            self.max_tokens, bucket["tokens"] + elapsed * self.refill_rate
        )
        bucket["last_refill"] = now
        return bucket

    def is_allowed(self, user_id: str, cost: float = 1.0) -> bool:
        """Check if request is allowed and consume a token."""
        bucket = self._get_bucket(user_id)
        if bucket["tokens"] >= cost:
            bucket["tokens"] -= cost
            return True
        return False

    def get_remaining(self, user_id: str) -> float:
        """Get remaining tokens for a user."""
        bucket = self._get_bucket(user_id)
        return bucket["tokens"]


# Global rate limiter instance
rate_limiter = RateLimiter(max_tokens=100, refill_rate=10.0)


# =============================================================================
# Performance Monitor
# =============================================================================
class PerformanceMonitor:
    """Tracks response times and request counts."""

    def __init__(self):
        self._metrics: Dict[str, List[float]] = defaultdict(list)
        self._request_counts: Dict[str, int] = defaultdict(int)
        self._error_counts: Dict[str, int] = defaultdict(int)

    def record_request(self, endpoint: str, response_time_ms: float, is_error: bool = False):
        """Record a request metric."""
        self._metrics[endpoint].append(response_time_ms)
        self._request_counts[endpoint] += 1
        if is_error:
            self._error_counts[endpoint] += 1
        # Keep only last 1000 entries per endpoint
        if len(self._metrics[endpoint]) > 1000:
            self._metrics[endpoint] = self._metrics[endpoint][-500:]

    def get_metrics(self) -> Dict[str, Any]:
        """Get aggregated metrics."""
        result = {}
        for endpoint, times in self._metrics.items():
            if not times:
                continue
            result[endpoint] = {
                "avg_ms": round(sum(times) / len(times), 2),
                "min_ms": round(min(times), 2),
                "max_ms": round(max(times), 2),
                "p95_ms": round(sorted(times)[int(len(times) * 0.95)] if times else 0, 2),
                "total_requests": self._request_counts[endpoint],
                "error_count": self._error_counts.get(endpoint, 0),
            }
        return result

    def get_summary(self) -> Dict[str, Any]:
        """Get a high-level summary."""
        total_requests = sum(self._request_counts.values())
        total_errors = sum(self._error_counts.values())
        all_times = [t for times in self._metrics.values() for t in times]
        return {
            "total_requests": total_requests,
            "total_errors": total_errors,
            "error_rate": round(total_errors / max(total_requests, 1) * 100, 2),
            "avg_response_ms": round(sum(all_times) / max(len(all_times), 1), 2),
            "endpoints_tracked": len(self._metrics),
        }


# Global performance monitor instance
performance_monitor = PerformanceMonitor()


# =============================================================================
# ZATCA Phase 2 Service
# =============================================================================
class ZATCAService:
    """ZATCA Phase 2 compliant UBL invoice (XML) generation.

    Hashing, the cryptographic stamp and Fatoora reporting live on the real
    sale-signing path (``services/zatca.py`` + ``services/zatca_sale.py``); this
    class only builds the unsigned UBL document those paths sign.
    """

    ZATCA_NS = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
    CAC_NS = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
    CBC_NS = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"

    def generate_xml_invoice(
        self,
        seller_name: str,
        seller_vat: str,
        buyer_name: str,
        buyer_vat: str,
        invoice_number: str,
        issue_date: str,
        issue_time: str,
        line_items: List[Dict[str, Any]],
        total_excluding_vat: float,
        total_vat: float,
        total_including_vat: float,
        payment_method: str = "10",  # Cash
        invoice_type_code: str = "388",  # 388 = Tax Invoice, 381 = Credit Note
        invoice_type_name: str = "0100000",
        billing_reference_id: Optional[str] = None,  # original invoice no. for 381
        previous_hash: Optional[str] = None,
        invoice_uuid: Optional[str] = None,
        tax_category_id: Optional[str] = None,
    ) -> str:
        """Generate ZATCA Phase 2 compliant UBL 2.1 XML invoice.

        ``tax_category_id`` optionally forces the UBL tax category ('S'/'Z'/'E');
        when omitted it is derived from the amounts (see ``derive_tax_category``) —
        standard when VAT was charged, zero-rated otherwise. Pass ``'E'`` for an
        exempt supply, which the amounts alone cannot distinguish from zero-rated.

        ``invoice_type_code`` 388 is a tax invoice; 381 is a credit note. For a
        credit note, pass ``billing_reference_id`` with the original invoice
        number so the document carries the required ``cac:BillingReference``
        linking the credit note back to the invoice it reverses (POS-07).

        ``previous_hash`` is the PIH (Previous Invoice Hash) embedded into the
        chaining element. It MUST be the invoking client's recorded chain head
        (``creds.pih`` / ``INITIAL_PIH`` for the first invoice). The fiscal chain
        is never held on this process-global service — passing it explicitly is
        what keeps interleaved tenants' chains from bleeding into each other (C1).

        ``invoice_uuid`` sets ``cbc:UUID``; the caller persists the same value so
        the embedded UUID, the stored ``ZatcaDocuments.invoice_uuid`` and the
        UUID submitted to Fatoora all agree (a fresh UUID is minted if omitted).
        """
        # Root element
        invoice = Element("Invoice")
        invoice.set("xmlns", self.ZATCA_NS)
        invoice.set("xmlns:cac", self.CAC_NS)
        invoice.set("xmlns:cbc", self.CBC_NS)

        # Profile ID (ZATCA reporting)
        profile_id = SubElement(invoice, "cbc:ProfileID")
        profile_id.text = "reporting:1.0"

        # Invoice ID
        inv_id = SubElement(invoice, "cbc:ID")
        inv_id.text = invoice_number

        # UUID — the caller persists this same value on ZatcaDocuments so the
        # cbc:UUID embedded here equals the stored invoice_uuid (and what is
        # submitted to Fatoora). Falls back to a fresh UUID for standalone use.
        inv_uuid = SubElement(invoice, "cbc:UUID")
        inv_uuid.text = invoice_uuid or str(uuid.uuid4())

        # Issue Date & Time
        issue_date_el = SubElement(invoice, "cbc:IssueDate")
        issue_date_el.text = issue_date
        issue_time_el = SubElement(invoice, "cbc:IssueTime")
        issue_time_el.text = issue_time

        # Invoice Type Code (388 = Tax Invoice, 381 = Credit Note)
        type_code = SubElement(invoice, "cbc:InvoiceTypeCode")
        type_code.text = invoice_type_code
        type_code.set("name", invoice_type_name)

        # Document Currency
        currency = SubElement(invoice, "cbc:DocumentCurrencyCode")
        currency.text = "SAR"

        # Billing Reference — links a credit note (381) to the original invoice.
        if billing_reference_id:
            billing_ref = SubElement(invoice, "cac:BillingReference")
            inv_doc_ref = SubElement(billing_ref, "cac:InvoiceDocumentReference")
            br_id = SubElement(inv_doc_ref, "cbc:ID")
            br_id.text = billing_reference_id

        # Previous Invoice Hash (for chaining)
        additional_doc = SubElement(invoice, "cac:AdditionalDocumentReference")
        doc_id = SubElement(additional_doc, "cbc:ID")
        doc_id.text = "PIH"
        attachment = SubElement(additional_doc, "cac:Attachment")
        embedded = SubElement(attachment, "cbc:EmbeddedDocumentBinaryObject")
        embedded.set("mimeCode", "text/plain")
        embedded.text = previous_hash or INITIAL_PIH

        # Supplier (Seller)
        supplier_party = SubElement(invoice, "cac:AccountingSupplierParty")
        party = SubElement(supplier_party, "cac:Party")
        party_name = SubElement(party, "cac:PartyName")
        name_el = SubElement(party_name, "cbc:Name")
        name_el.text = seller_name
        tax_scheme = SubElement(party, "cac:PartyTaxScheme")
        company_id = SubElement(tax_scheme, "cbc:CompanyID")
        company_id.text = seller_vat
        scheme = SubElement(tax_scheme, "cac:TaxScheme")
        scheme_id = SubElement(scheme, "cbc:ID")
        scheme_id.text = "VAT"

        # Customer (Buyer)
        customer_party = SubElement(invoice, "cac:AccountingCustomerParty")
        cust_party = SubElement(customer_party, "cac:Party")
        cust_party_name = SubElement(cust_party, "cac:PartyName")
        cust_name_el = SubElement(cust_party_name, "cbc:Name")
        cust_name_el.text = buyer_name
        if buyer_vat:
            cust_tax = SubElement(cust_party, "cac:PartyTaxScheme")
            cust_comp_id = SubElement(cust_tax, "cbc:CompanyID")
            cust_comp_id.text = buyer_vat
            cust_scheme = SubElement(cust_tax, "cac:TaxScheme")
            cust_scheme_id = SubElement(cust_scheme, "cbc:ID")
            cust_scheme_id.text = "VAT"

        # Payment Means
        payment_means = SubElement(invoice, "cac:PaymentMeans")
        payment_code = SubElement(payment_means, "cbc:PaymentMeansCode")
        payment_code.text = payment_method

        # Tax Total
        tax_total = SubElement(invoice, "cac:TaxTotal")
        tax_amount = SubElement(tax_total, "cbc:TaxAmount")
        tax_amount.set("currencyID", "SAR")
        tax_amount.text = f"{total_vat:.2f}"

        tax_subtotal = SubElement(tax_total, "cac:TaxSubtotal")
        taxable_amount = SubElement(tax_subtotal, "cbc:TaxableAmount")
        taxable_amount.set("currencyID", "SAR")
        taxable_amount.text = f"{total_excluding_vat:.2f}"
        sub_tax_amount = SubElement(tax_subtotal, "cbc:TaxAmount")
        sub_tax_amount.set("currencyID", "SAR")
        sub_tax_amount.text = f"{total_vat:.2f}"
        tax_category = SubElement(tax_subtotal, "cac:TaxCategory")
        # Derive category + percent from the real amounts so the tax block can
        # never contradict the money (FIS-01): a zero-rated/exempt sale renders
        # 0.00 / 'Z' (or 'E'), a standard sale its actual effective rate.
        cat_text, percent_text = derive_tax_category(
            total_excluding_vat, total_vat, category_id=tax_category_id
        )
        cat_id = SubElement(tax_category, "cbc:ID")
        cat_id.text = cat_text
        percent = SubElement(tax_category, "cbc:Percent")
        percent.text = percent_text
        cat_scheme = SubElement(tax_category, "cac:TaxScheme")
        cat_scheme_id = SubElement(cat_scheme, "cbc:ID")
        cat_scheme_id.text = "VAT"

        # Legal Monetary Total
        monetary = SubElement(invoice, "cac:LegalMonetaryTotal")
        line_ext = SubElement(monetary, "cbc:LineExtensionAmount")
        line_ext.set("currencyID", "SAR")
        line_ext.text = f"{total_excluding_vat:.2f}"
        tax_excl = SubElement(monetary, "cbc:TaxExclusiveAmount")
        tax_excl.set("currencyID", "SAR")
        tax_excl.text = f"{total_excluding_vat:.2f}"
        tax_incl = SubElement(monetary, "cbc:TaxInclusiveAmount")
        tax_incl.set("currencyID", "SAR")
        tax_incl.text = f"{total_including_vat:.2f}"
        payable = SubElement(monetary, "cbc:PayableAmount")
        payable.set("currencyID", "SAR")
        payable.text = f"{total_including_vat:.2f}"

        # Invoice Lines
        for idx, item in enumerate(line_items, 1):
            line = SubElement(invoice, "cac:InvoiceLine")
            line_id = SubElement(line, "cbc:ID")
            line_id.text = str(idx)
            qty = SubElement(line, "cbc:InvoicedQuantity")
            qty.set("unitCode", "PCE")
            qty.text = str(item.get("quantity", 1))
            line_amount = SubElement(line, "cbc:LineExtensionAmount")
            line_amount.set("currencyID", "SAR")
            item_total = item.get("price", 0) * item.get("quantity", 1)
            line_amount.text = f"{item_total:.2f}"

            # Item details
            inv_item = SubElement(line, "cac:Item")
            item_name = SubElement(inv_item, "cbc:Name")
            item_name.text = item.get("name", f"Item {idx}")

            # Price
            price_el = SubElement(line, "cac:Price")
            price_amount = SubElement(price_el, "cbc:PriceAmount")
            price_amount.set("currencyID", "SAR")
            price_amount.text = f"{item.get('price', 0):.2f}"

        # Generate XML bytes
        xml_bytes = tostring(invoice, encoding="unicode", xml_declaration=False)
        xml_declaration = '<?xml version="1.0" encoding="UTF-8"?>\n'
        full_xml = xml_declaration + xml_bytes

        # No fiscal chain state is held here: the caller computes the invoice hash
        # over this XML and advances the per-client chain (``creds.pih``). This
        # service stays stateless w.r.t. the PIH so concurrent tenants never bleed.
        return full_xml


# Global ZATCA service instance
zatca_service = ZATCAService()


# =============================================================================
# PDF Invoice Service (Arabic-only, ZATCA Compliant)
# =============================================================================
class PDFInvoiceService:
    """Generates Arabic-only ZATCA-compliant invoice HTML for PDF conversion."""

    @staticmethod
    def generate_invoice_html(
        seller_name: str,
        seller_vat: str,
        buyer_name: str,
        invoice_number: str,
        issue_date: str,
        line_items: List[Dict[str, Any]],
        subtotal: float,
        vat_amount: float,
        total_amount: float,
        zatca_qr: str,
        discount: float = 0,
        buyer_vat: str = "",
    ) -> str:
        """Generate Arabic-only HTML invoice suitable for PDF conversion.

        ``buyer_vat`` renders the B2B buyer tax block (PRN-02) when present; it is
        omitted for ordinary B2C invoices.
        """
        items_html = ""
        for idx, item in enumerate(line_items, 1):
            item_total = item.get("price", 0) * item.get("quantity", 1)
            items_html += f"""
            <tr>
                <td>{to_arabic_digits(idx)}</td>
                <td>{item.get('name', '')}</td>
                <td>{to_arabic_digits(item.get('quantity', 1))}</td>
                <td>{format_money_ar(item.get('price', 0))} ⃁</td>
                <td>{format_money_ar(item_total)} ⃁</td>
            </tr>"""

        buyer_vat_html = (
            f"<p><strong>الرقم الضريبي:</strong> {buyer_vat}</p>" if buyer_vat else ""
        )

        html = f"""<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <style>
        {_riyal_font_face()}
        body {{ font-family: 'Saudi Riyal', 'Noto Sans Arabic', 'Arial', sans-serif; direction: rtl; padding: 20px; }}
        .header {{ text-align: center; border-bottom: 2px solid #333; padding-bottom: 10px; }}
        .header h1 {{ margin: 0; font-size: 24px; }}
        .info {{ display: flex; justify-content: space-between; margin: 15px 0; }}
        .info-block {{ width: 48%; }}
        table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: center; }}
        th {{ background-color: #f5f5f5; font-weight: bold; }}
        .totals {{ text-align: left; margin-top: 15px; }}
        .totals table {{ width: 300px; margin-right: auto; }}
        .qr-section {{ text-align: center; margin-top: 20px; }}
        .zatca-notice {{ text-align: center; font-size: 12px; color: #666; margin-top: 10px; }}
        .stamp {{ border: 2px solid #333; padding: 5px 15px; display: inline-block; margin-top: 10px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>فاتورة ضريبية</h1>
        <p>Tax Invoice</p>
    </div>

    <div class="info">
        <div class="info-block">
            <h3>البائع</h3>
            <p><strong>الاسم:</strong> {seller_name}</p>
            <p><strong>الرقم الضريبي:</strong> {seller_vat}</p>
        </div>
        <div class="info-block">
            <h3>المشتري</h3>
            <p><strong>الاسم:</strong> {buyer_name}</p>
            {buyer_vat_html}
        </div>
    </div>

    <div>
        <p><strong>رقم الفاتورة:</strong> {invoice_number}</p>
        <p><strong>التاريخ:</strong> {to_arabic_digits(issue_date)}</p>
    </div>

    <table>
        <thead>
            <tr>
                <th>#</th>
                <th>الصنف</th>
                <th>الكمية</th>
                <th>السعر</th>
                <th>الإجمالي</th>
            </tr>
        </thead>
        <tbody>
            {items_html}
        </tbody>
    </table>

    <div class="totals">
        <table>
            <tr><td>المجموع الفرعي</td><td>{format_money_ar(subtotal)} ⃁</td></tr>
            <tr><td>الخصم</td><td>{format_money_ar(discount)} ⃁</td></tr>
            <tr><td>ضريبة القيمة المضافة (15٪)</td><td>{format_money_ar(vat_amount)} ⃁</td></tr>
            <tr><td><strong>الإجمالي</strong></td><td><strong>{format_money_ar(total_amount)} ⃁</strong></td></tr>
        </table>
    </div>

    <div class="qr-section">
        <p><strong>رمز الاستجابة السريعة (ZATCA):</strong></p>
        <p style="font-family: monospace; font-size: 10px; word-break: break-all;">{zatca_qr}</p>
    </div>

    <div class="zatca-notice">
        <div class="stamp">فاتورة إلكترونية متوافقة مع هيئة الزكاة والضريبة والجمارك</div>
        <p>ZATCA Compliant E-Invoice</p>
    </div>
</body>
</html>"""
        return html

    @staticmethod
    def generate_quotation_html(
        seller_name: str,
        seller_vat: str,
        buyer_name: str,
        quote_number: str,
        issue_date: str,
        valid_until: str,
        line_items: List[Dict[str, Any]],
        subtotal: float,
        vat_amount: float,
        total_amount: float,
        discount: float = 0,
        notes: str = "",
    ) -> str:
        """Generate an **always-Arabic** price-quotation (عرض سعر) document.

        Per the SRS "receipts/quotations always Arabic" rule (§7) this is rendered
        RTL/Arabic with Arabic-Indic numerals regardless of UI language. A
        quotation is **not** a fiscal document, so — unlike the tax invoice — it
        carries no ZATCA QR or cryptographic stamp and is clearly labelled
        "غير ضريبية / not a tax invoice".
        """
        items_html = ""
        for idx, item in enumerate(line_items, 1):
            item_total = item.get("price", 0) * item.get("quantity", 1)
            items_html += f"""
            <tr>
                <td>{to_arabic_digits(idx)}</td>
                <td>{item.get('name', '')}</td>
                <td>{to_arabic_digits(item.get('quantity', 1))}</td>
                <td>{format_money_ar(item.get('price', 0))} ⃁</td>
                <td>{format_money_ar(item_total)} ⃁</td>
            </tr>"""

        notes_html = (
            f'<div class="notes"><strong>ملاحظات:</strong> {notes}</div>' if notes else ""
        )

        html = f"""<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <style>
        {_riyal_font_face()}
        body {{ font-family: 'Saudi Riyal', 'Noto Sans Arabic', 'Arial', sans-serif; direction: rtl; padding: 20px; }}
        .header {{ text-align: center; border-bottom: 2px solid #333; padding-bottom: 10px; }}
        .header h1 {{ margin: 0; font-size: 24px; }}
        .info {{ display: flex; justify-content: space-between; margin: 15px 0; }}
        .info-block {{ width: 48%; }}
        table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: center; }}
        th {{ background-color: #f5f5f5; font-weight: bold; }}
        .totals {{ text-align: left; margin-top: 15px; }}
        .totals table {{ width: 300px; margin-right: auto; }}
        .notes {{ margin-top: 15px; font-size: 13px; }}
        .notice {{ text-align: center; font-size: 12px; color: #666; margin-top: 15px; }}
        .stamp {{ border: 2px solid #333; padding: 5px 15px; display: inline-block; margin-top: 10px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>عرض سعر</h1>
        <p>Price Quotation</p>
    </div>

    <div class="info">
        <div class="info-block">
            <h3>البائع</h3>
            <p><strong>الاسم:</strong> {seller_name}</p>
            <p><strong>الرقم الضريبي:</strong> {seller_vat}</p>
        </div>
        <div class="info-block">
            <h3>العميل</h3>
            <p><strong>الاسم:</strong> {buyer_name}</p>
        </div>
    </div>

    <div>
        <p><strong>رقم العرض:</strong> {quote_number}</p>
        <p><strong>التاريخ:</strong> {to_arabic_digits(issue_date)}</p>
        <p><strong>صالح حتى:</strong> {to_arabic_digits(valid_until) if valid_until else "—"}</p>
    </div>

    <table>
        <thead>
            <tr>
                <th>#</th>
                <th>الصنف</th>
                <th>الكمية</th>
                <th>السعر</th>
                <th>الإجمالي</th>
            </tr>
        </thead>
        <tbody>
            {items_html}
        </tbody>
    </table>

    <div class="totals">
        <table>
            <tr><td>المجموع الفرعي</td><td>{format_money_ar(subtotal)} ⃁</td></tr>
            <tr><td>الخصم</td><td>{format_money_ar(discount)} ⃁</td></tr>
            <tr><td>ضريبة القيمة المضافة</td><td>{format_money_ar(vat_amount)} ⃁</td></tr>
            <tr><td><strong>الإجمالي التقديري</strong></td><td><strong>{format_money_ar(total_amount)} ⃁</strong></td></tr>
        </table>
    </div>

    {notes_html}

    <div class="notice">
        <div class="stamp">هذا المستند عرض سعر وليس فاتورة ضريبية</div>
        <p>This document is a price quotation, not a tax invoice.</p>
    </div>
</body>
</html>"""
        return html

    # Arabic labels for the Saudi tender taxonomy (PAY-01..04). Used by the
    # always-Arabic Z-report so "sales by tender" reads in Arabic regardless of
    # the cashier's UI language (L10N-06 / PRN-05).
    _TENDER_LABELS_AR = {
        "cash": "نقدي",
        "card": "بطاقة",
        "mada": "مدى",
        "applepay": "Apple Pay",
        "stcpay": "STC Pay",
        "tabby": "تابي",
        "tamara": "تمارا",
        "transfer": "تحويل بنكي",
        "loyalty": "نقاط الولاء",
        "refund": "استرجاع",
    }

    @staticmethod
    def generate_zreport_html(business_name: str, data: Dict[str, Any]) -> str:
        """Generate the **always-Arabic** Z-report / X-report printable (PRN-05).

        ``data`` is the structure produced by the ``/reports/zreport`` aggregator:
        the shift header, sales-by-tender breakdown, VAT/discount/void/refund
        totals and the cash drawer reconciliation (expected vs counted + variance).
        Per the fiscal-document rule (SRS §7 / L10N-06) it renders RTL/Arabic with
        Arabic-Indic numerals regardless of the UI language. A Z-report is a
        management/fiscal-close document, not a tax invoice, so it carries **no**
        ZATCA QR or cryptographic stamp.
        """
        shift = data.get("shift", {})
        totals = data.get("totals", {})
        cash = data.get("cash", {})
        report_type = data.get("report_type", "Z")

        is_close = report_type == "Z"
        title_ar = "تقرير إغلاق الوردية (Z)" if is_close else "تقرير الوردية الحالية (X)"
        title_en = "Z-Report (Shift Close)" if is_close else "X-Report (Current Shift)"

        tender_rows = ""
        for tender in data.get("tenders", []):
            label = PDFInvoiceService._TENDER_LABELS_AR.get(
                tender.get("tender_type", ""), tender.get("tender_type", "")
            )
            tender_rows += f"""
            <tr>
                <td>{label}</td>
                <td>{to_arabic_digits(tender.get('count', 0))}</td>
                <td>{format_money_ar(tender.get('amount', 0))} ⃁</td>
            </tr>"""
        if not tender_rows:
            tender_rows = '<tr><td colspan="3">لا توجد مبيعات</td></tr>'

        # Reconciliation badge — only meaningful once the drawer has been counted.
        recon = cash.get("reconciliation")
        recon_ar = {"balanced": "مطابق", "over": "زيادة", "short": "عجز"}.get(recon or "", "—")
        counted_html = (
            f"<tr><td>النقد المحسوب</td><td>{format_money_ar(cash.get('counted_cash', 0))} ⃁</td></tr>"
            if cash.get("counted_cash") is not None
            else ""
        )
        variance_html = (
            f"<tr><td><strong>الفرق ({recon_ar})</strong></td>"
            f"<td><strong>{format_money_ar(cash.get('variance', 0))} ⃁</strong></td></tr>"
            if cash.get("variance") is not None
            else "<tr><td colspan='2'>لم يتم جرد الدرج بعد</td></tr>"
        )

        html = f"""<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <style>
        {_riyal_font_face()}
        body {{ font-family: 'Saudi Riyal', 'Noto Sans Arabic', 'Arial', sans-serif; direction: rtl; padding: 20px; }}
        .header {{ text-align: center; border-bottom: 2px solid #333; padding-bottom: 10px; }}
        .header h1 {{ margin: 0; font-size: 22px; }}
        .meta {{ margin: 15px 0; font-size: 14px; }}
        .meta p {{ margin: 4px 0; }}
        h3 {{ border-bottom: 1px solid #ccc; padding-bottom: 4px; margin-top: 20px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 10px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: center; }}
        th {{ background-color: #f5f5f5; font-weight: bold; }}
        .totals table, .cash table {{ width: 360px; margin-right: auto; }}
        .notice {{ text-align: center; font-size: 12px; color: #666; margin-top: 20px; }}
        .stamp {{ border: 2px solid #333; padding: 5px 15px; display: inline-block; margin-top: 10px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{title_ar}</h1>
        <p>{title_en} — {business_name}</p>
    </div>

    <div class="meta">
        <p><strong>رقم الوردية:</strong> {to_arabic_digits(shift.get('id', ''))}</p>
        <p><strong>الكاشير:</strong> {shift.get('staff_name') or '—'}</p>
        <p><strong>وقت الفتح:</strong> {to_arabic_digits(shift.get('start_time') or '—')}</p>
        <p><strong>وقت الإغلاق:</strong> {to_arabic_digits(shift.get('end_time') or '—')}</p>
    </div>

    <h3>المبيعات حسب طريقة الدفع</h3>
    <table>
        <thead>
            <tr><th>طريقة الدفع</th><th>العدد</th><th>المبلغ</th></tr>
        </thead>
        <tbody>{tender_rows}</tbody>
    </table>

    <h3>الإجماليات</h3>
    <div class="totals">
        <table>
            <tr><td>إجمالي المبيعات ({to_arabic_digits(totals.get('sale_count', 0))} فاتورة)</td><td>{format_money_ar(totals.get('gross_sales', 0))} ⃁</td></tr>
            <tr><td>المرتجعات ({to_arabic_digits(totals.get('refund_count', 0))})</td><td>{format_money_ar(totals.get('refunds', 0))} ⃁</td></tr>
            <tr><td>الإلغاءات ({to_arabic_digits(totals.get('void_count', 0))})</td><td>{format_money_ar(totals.get('voids', 0))} ⃁</td></tr>
            <tr><td>الخصومات</td><td>{format_money_ar(totals.get('discounts', 0))} ⃁</td></tr>
            <tr><td>البقشيش (خارج وعاء الضريبة)</td><td>{format_money_ar(totals.get('tips', 0))} ⃁</td></tr>
            <tr><td>ضريبة القيمة المضافة المحصّلة</td><td>{format_money_ar(totals.get('vat_collected', 0))} ⃁</td></tr>
            <tr><td>ضريبة القيمة المضافة المعكوسة</td><td>{format_money_ar(totals.get('vat_reversed', 0))} ⃁</td></tr>
            <tr><td><strong>صافي المبيعات</strong></td><td><strong>{format_money_ar(totals.get('net_sales', 0))} ⃁</strong></td></tr>
        </table>
    </div>

    <h3>تسوية النقدية في الدرج</h3>
    <div class="cash">
        <table>
            <tr><td>النقد الافتتاحي</td><td>{format_money_ar(cash.get('opening_cash', 0))} ⃁</td></tr>
            <tr><td>مبيعات نقدية</td><td>{format_money_ar(cash.get('cash_sales', 0))} ⃁</td></tr>
            <tr><td>مرتجعات نقدية</td><td>{format_money_ar(cash.get('cash_refunds', 0))} ⃁</td></tr>
            <tr><td>إيداع نقدي بالدرج</td><td>{format_money_ar(cash.get('pay_in', 0))} ⃁</td></tr>
            <tr><td>مدفوعات نقدية من الدرج</td><td>{format_money_ar(cash.get('pay_out', 0))} ⃁</td></tr>
            <tr><td>سحب نقدي للخزنة</td><td>{format_money_ar(cash.get('cash_drops', 0))} ⃁</td></tr>
            <tr><td><strong>النقد المتوقع</strong></td><td><strong>{format_money_ar(cash.get('expected_cash', 0))} ⃁</strong></td></tr>
            {counted_html}
            {variance_html}
        </table>
    </div>

    <div class="notice">
        <div class="stamp">تقرير إداري — ليس فاتورة ضريبية</div>
        <p>Management report — not a tax invoice.</p>
    </div>
</body>
</html>"""
        return html


# =============================================================================
# Email Service (Stub with Logging)
# =============================================================================
class EmailService:
    """Email notification service.

    Phase 3: delegates to :mod:`core.email`, which sends via real SMTP when
    ``SMTP_HOST`` is configured and otherwise logs the message (dev fallback).
    The return shape is preserved so existing callers keep working; ``status`` is
    ``"sent"`` when delivered over SMTP and ``"logged"`` on the dev fallback.
    """

    @staticmethod
    async def send_email(
        to_email: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send an email notification via the configured transport."""
        from core.email import send_email as _send_email

        message_id = str(uuid.uuid4())
        delivered = await _send_email(to_email, subject, body)
        return {
            "message_id": message_id,
            "status": "sent" if delivered else "logged",
            "to": to_email,
            "subject": subject,
            "delivered": delivered,
        }

    @staticmethod
    async def send_low_stock_alert(
        to_email: str, product_name: str, current_stock: int, threshold: int
    ) -> Dict[str, Any]:
        """Send low stock alert email."""
        subject = f"تنبيه: مخزون منخفض - {product_name}"
        body = (
            f"المنتج: {product_name}\n"
            f"المخزون الحالي: {current_stock}\n"
            f"الحد الأدنى: {threshold}\n"
            f"يرجى إعادة التزويد."
        )
        return await EmailService.send_email(to_email, subject, body)

    @staticmethod
    async def send_transaction_receipt(
        to_email: str, invoice_number: str, total: float
    ) -> Dict[str, Any]:
        """Send transaction receipt email."""
        subject = f"إيصال المعاملة - {invoice_number}"
        body = f"رقم الفاتورة: {invoice_number}\nالإجمالي: {total:.2f} ⃁"
        return await EmailService.send_email(to_email, subject, body)


# =============================================================================
# Webhook Dispatcher
# =============================================================================

# Canonical set of advertised webhook events (ISSUE-051, H25). The
# WebhookManagement UI's ``AVAILABLE_EVENTS`` must mirror this list exactly, and
# every entry here is fired at its source so a subscriber never signs up for an
# event that silently never arrives. ``sale.refunded`` (not ``refund.created``)
# is the agreed name on both sides.
WEBHOOK_EVENTS = [
    "sale.completed",
    "sale.refunded",
    "product.created",
    "product.updated",
    "product.low_stock",
    "customer.created",
    "shift.opened",
    "shift.closed",
    "inventory.updated",
]


class WebhookDispatcher:
    """Fires webhooks with HMAC signatures for event notifications."""

    @staticmethod
    def generate_signature(payload: str, secret: str) -> str:
        """Generate HMAC-SHA256 signature for webhook payload."""
        return hmac.new(
            secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    MAX_ATTEMPTS = 3
    TIMEOUT_SECONDS = 10.0

    @staticmethod
    async def dispatch(
        url: str,
        event: str,
        payload: Dict[str, Any],
        secret: str,
    ) -> Dict[str, Any]:
        """POST a signed webhook to ``url`` with bounded retries (Phase 3).

        The body is HMAC-SHA256 signed with the endpoint ``secret`` and sent in
        the ``X-Webhook-Signature: sha256=<hex>`` header (GitHub-style) so the
        receiver can verify authenticity. Transient failures (network error or
        5xx) are retried up to ``MAX_ATTEMPTS``; a 4xx is treated as a permanent
        rejection and not retried. Never raises — delivery outcome is returned.
        """
        import httpx

        payload_str = json.dumps(payload, ensure_ascii=False, default=str)
        signature = WebhookDispatcher.generate_signature(payload_str, secret or "")
        delivery_id = str(uuid.uuid4())
        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Signature": f"sha256={signature}",
            "X-Webhook-Event": event,
            "X-Webhook-Delivery": delivery_id,
        }

        last_error: Optional[str] = None
        status_code: Optional[int] = None
        started = time.monotonic()
        for attempt in range(1, WebhookDispatcher.MAX_ATTEMPTS + 1):
            try:
                async with httpx.AsyncClient(timeout=WebhookDispatcher.TIMEOUT_SECONDS) as http:
                    resp = await http.post(url, content=payload_str.encode("utf-8"), headers=headers)
                status_code = resp.status_code
                if 200 <= status_code < 300:
                    return {
                        "delivery_id": delivery_id,
                        "url": url,
                        "event": event,
                        "status": "delivered",
                        "status_code": status_code,
                        "response_time_ms": int((time.monotonic() - started) * 1000),
                        "attempts": attempt,
                        "signature": f"sha256={signature}",
                    }
                if 400 <= status_code < 500:
                    # Permanent rejection — do not retry.
                    last_error = f"HTTP {status_code}"
                    break
                last_error = f"HTTP {status_code}"
            except Exception as exc:  # network error / timeout — retry
                last_error = type(exc).__name__

        logger.warning(
            "WEBHOOK_DELIVERY_FAILED url=%s event=%s error=%s", url, event, last_error
        )
        return {
            "delivery_id": delivery_id,
            "url": url,
            "event": event,
            "status": "failed",
            "status_code": status_code,
            "response_time_ms": int((time.monotonic() - started) * 1000),
            "attempts": WebhookDispatcher.MAX_ATTEMPTS,
            "error": last_error,
            "signature": f"sha256={signature}",
        }


async def fire_event(
    db: AsyncSession, user_id: str, event: str, payload: Dict[str, Any]
) -> int:
    """Publish ``event`` onto the internal event bus and return endpoints attempted.

    Since ISSUE-218 this is a thin shim over :func:`services.event_bus.publish`:
    the bus fans the event out to every subscriber, the canonical one being the
    outbound-webhook dispatcher, which enqueues one durable ``webhook.deliver``
    job per active endpoint whose ``events`` (comma- or JSON-list) include the
    event (or the wildcard ``*``). The return value is the number of webhook
    endpoints scheduled — the same "attempted" contract callers and tests relied
    on. Best effort — a misconfigured webhook never breaks the originating
    sale/refund. Intended to be scheduled via ``BackgroundTasks`` after commit.
    """
    from services import event_bus

    return await event_bus.publish(db, str(user_id), event, payload)


async def record_delivery(
    db: AsyncSession,
    user_id: str,
    webhook_id: Optional[int],
    url: str,
    event: str,
    result: Optional[Dict[str, Any]],
) -> None:
    """Persist a single ``WebhookDispatcher.dispatch`` outcome (ISSUE-029).

    Best effort — a logging failure (or a missing key in a stubbed result) must
    never break the originating dispatch. ``result`` is the dict returned by
    ``dispatch``; ``status`` is "delivered" only on a 2xx.
    """
    from models.webhook_deliveries import Webhook_deliveries

    result = result or {}
    status = result.get("status") or "failed"
    try:
        db.add(
            Webhook_deliveries(
                user_id=user_id,
                webhook_id=webhook_id,
                event=event,
                target_url=url,
                status=status,
                status_code=result.get("status_code"),
                response_time_ms=result.get("response_time_ms"),
                attempts=result.get("attempts"),
                error=result.get("error"),
            )
        )
        await db.commit()
    except Exception as exc:  # pragma: no cover - logging must not break dispatch
        logger.warning("Webhook delivery log write failed for %s: %s", event, exc)
        await db.rollback()


async def fire_event_background(user_id: str, event: str, payload: Dict[str, Any]) -> None:
    """``BackgroundTasks``-friendly wrapper that opens its own DB session.

    The request-scoped session is closed once the response is sent, so domain
    events fired post-commit must use a fresh session.
    """
    from core.database import db_manager

    try:
        await db_manager.ensure_initialized()
        async with db_manager.async_session_maker() as db:
            await fire_event(db, user_id, event, payload)
    except Exception as exc:  # pragma: no cover - background dispatch is best effort
        logger.warning("Background webhook dispatch failed for %s: %s", event, exc)


def _hook_subscribes(events_field: Optional[str], event: str) -> bool:
    """Return whether a webhook's ``events`` column subscribes to ``event``."""
    if not events_field:
        return False
    raw = events_field.strip()
    subscribed: list = []
    if raw.startswith("["):
        try:
            subscribed = json.loads(raw)
        except (ValueError, TypeError):
            subscribed = []
    if not subscribed:
        subscribed = [e.strip() for e in raw.split(",") if e.strip()]
    return "*" in subscribed or event in subscribed


# =============================================================================
# Low Stock Checker
# =============================================================================
class LowStockChecker:
    """Checks inventory thresholds and generates alerts."""

    DEFAULT_THRESHOLD = 10

    @staticmethod
    async def check_low_stock(
        db: AsyncSession, user_id: str, threshold: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Check for products below stock threshold."""
        from models.products import Products

        min_qty = threshold if threshold is not None else LowStockChecker.DEFAULT_THRESHOLD

        result = await db.execute(
            select(Products).where(
                Products.user_id == user_id,
                Products.quantity <= min_qty,
                Products.is_active == True,  # noqa: E712
            )
        )
        products = result.scalars().all()

        alerts = []
        for p in products:
            alerts.append({
                "product_id": p.id,
                "name": p.name,
                "name_ar": p.name_ar,
                "current_stock": p.quantity,
                "threshold": min_qty,
                "severity": "critical" if p.quantity <= 0 else "warning",
                "barcode": p.barcode,
            })

        return alerts


# =============================================================================
# Bulk Import Service
# =============================================================================
class BulkImportService:
    """Parses CSV data for bulk import of products and customers."""

    @staticmethod
    def parse_csv(csv_content: str) -> List[Dict[str, str]]:
        """Parse CSV string content into list of dictionaries."""
        reader = csv.DictReader(io.StringIO(csv_content))
        rows = []
        for row in reader:
            # Strip whitespace from keys and values
            cleaned = {k.strip(): v.strip() for k, v in row.items() if k}
            rows.append(cleaned)
        return rows

    @staticmethod
    def validate_product_rows(rows: List[Dict[str, str]]) -> Dict[str, Any]:
        """Validate product CSV rows."""
        errors = []
        valid_rows = []
        required_fields = ["name", "price"]

        for idx, row in enumerate(rows):
            row_errors = []
            for field in required_fields:
                if field not in row or not row[field]:
                    row_errors.append(f"Missing required field: {field}")

            if "price" in row and row["price"]:
                try:
                    float(row["price"])
                except ValueError:
                    row_errors.append("Invalid price format")

            if "quantity" in row and row["quantity"]:
                try:
                    int(row["quantity"])
                except ValueError:
                    row_errors.append("Invalid quantity format")

            if row_errors:
                errors.append({"row": idx + 1, "errors": row_errors})
            else:
                valid_rows.append(row)

        return {
            "valid_count": len(valid_rows),
            "error_count": len(errors),
            "valid_rows": valid_rows,
            "errors": errors,
        }

    @staticmethod
    def validate_customer_rows(rows: List[Dict[str, str]]) -> Dict[str, Any]:
        """Validate customer CSV rows."""
        errors = []
        valid_rows = []
        required_fields = ["name"]

        for idx, row in enumerate(rows):
            row_errors = []
            for field in required_fields:
                if field not in row or not row[field]:
                    row_errors.append(f"Missing required field: {field}")

            if row_errors:
                errors.append({"row": idx + 1, "errors": row_errors})
            else:
                valid_rows.append(row)

        return {
            "valid_count": len(valid_rows),
            "error_count": len(errors),
            "valid_rows": valid_rows,
            "errors": errors,
        }

    @staticmethod
    def generate_csv_export(data: List[Dict[str, Any]]) -> str:
        """Generate CSV string from list of dictionaries."""
        if not data:
            return ""
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)
        return output.getvalue()


# =============================================================================
# Search Service
# =============================================================================
class SearchService:
    """Full-text search across entities (products, customers, transactions)."""

    @staticmethod
    async def global_search(
        db: AsyncSession, user_id: str, query: str, limit: int = 20
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Search across products, customers, and transactions."""
        from models.customers import Customers
        from models.products import Products
        from models.transactions import Transactions

        results: Dict[str, List[Dict[str, Any]]] = {
            "products": [],
            "customers": [],
            "transactions": [],
        }
        search_pattern = f"%{query}%"

        # Search products
        prod_result = await db.execute(
            select(Products)
            .where(
                Products.user_id == user_id,
                or_(
                    Products.name.ilike(search_pattern),
                    Products.name_ar.ilike(search_pattern),
                    Products.barcode.ilike(search_pattern),
                    Products.category.ilike(search_pattern),
                ),
            )
            .limit(limit)
        )
        for p in prod_result.scalars().all():
            results["products"].append({
                "id": p.id,
                "name": p.name,
                "name_ar": p.name_ar,
                "barcode": p.barcode,
                "price": p.price,
                "category": p.category,
            })

        # Search customers
        cust_result = await db.execute(
            select(Customers)
            .where(
                Customers.user_id == user_id,
                or_(
                    Customers.name.ilike(search_pattern),
                    Customers.phone.ilike(search_pattern),
                    Customers.email.ilike(search_pattern),
                ),
            )
            .limit(limit)
        )
        for c in cust_result.scalars().all():
            results["customers"].append({
                "id": c.id,
                "name": c.name,
                "phone": c.phone,
                "email": c.email,
            })

        # Search transactions
        txn_result = await db.execute(
            select(Transactions)
            .where(
                Transactions.user_id == user_id,
                or_(
                    Transactions.invoice_number.ilike(search_pattern),
                    Transactions.customer_name.ilike(search_pattern),
                    Transactions.customer_phone.ilike(search_pattern),
                ),
            )
            .limit(limit)
        )
        for t in txn_result.scalars().all():
            results["transactions"].append({
                "id": t.id,
                "invoice_number": t.invoice_number,
                "total_amount": t.total_amount,
                "customer_name": t.customer_name,
                "status": t.status,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            })

        return results


# =============================================================================
# Offline Sync Service
# =============================================================================
class OfflineSyncService:
    """Processes queued offline transactions when device reconnects."""

    @staticmethod
    async def process_offline_queue(
        db: AsyncSession,
        user_id: str,
        client_id: int,
        queued_transactions: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Process a batch of offline-queued sales (POS-05).

        Each sale is routed through the **full** atomic path (inventory
        deduction, invoice counter, shift accumulation, ECDSA signing + hash
        chaining) and deduplicated by ``offline_id`` — so an offline sale is
        fiscally identical to one rung up live, and re-syncing is idempotent.
        A failing item is rolled back and reported without dropping the others.
        """
        # Imported lazily: routers.pos imports services.production at load time,
        # so importing it at module scope here would be circular.
        from routers.pos import process_offline_sale

        processed = 0
        skipped = 0
        errors = []
        results: List[Dict[str, Any]] = []
        # DAT-06 / FE-03: the offline_ids the server has durably settled (booked
        # now or already booked on a prior sync). The frontend deletes ONLY these
        # from its queue and retries/surfaces the rest, so a partially-accepted
        # batch never silently drops a rejected sale.
        accepted_offline_ids: List[str] = []

        for idx, txn in enumerate(queued_transactions):
            try:
                outcome = await process_offline_sale(db, user_id, client_id, txn)
                if outcome["status"] == "skipped":
                    skipped += 1
                else:
                    processed += 1
                results.append(outcome)
                if outcome.get("offline_id") is not None:
                    accepted_offline_ids.append(outcome["offline_id"])
            except Exception as e:
                await db.rollback()
                errors.append(
                    {"index": idx, "offline_id": txn.get("offline_id"), "error": str(e)}
                )

        return {
            "processed": processed,
            "skipped_duplicates": skipped,
            "errors": errors,
            "results": results,
            "accepted_offline_ids": accepted_offline_ids,
            "total_submitted": len(queued_transactions),
        }


# =============================================================================
# Shift cash-drawer reconciliation (POS-09, F-009)
# =============================================================================
async def compute_shift_cash_reconciliation(db: AsyncSession, shift) -> Dict[str, float]:
    """Compute the expected cash drawer for a shift from **cash tenders only**.

    The physical drawer holds the opening float plus cash taken in, minus cash
    paid back out (refunds) — it never holds card/Mada/transfer/BNPL money. So
    reconciling against gross sales (``opening + total_sales``) overstates the
    expected cash by every non-cash sale, making the close-time variance wrong
    whenever any non-cash sale occurred (POS-09 drawer reconciliation).

    Cash is summed from the real captured ``payment_tenders`` rows (F-001),
    falling back to a legacy sale's ``payment_method == 'cash'`` when it predates
    tender capture so historical shifts still reconcile. With refund-to-origin
    wired (F-004), only the **cash** portion of a refund is cash paid out of the
    drawer — a card/Mada refund goes back to the card via the gateway, so it is
    read from the credit note's ``refunded`` tender rows (a legacy credit note with
    no recorded refund tenders still falls back to its full total as cash out).
    Cash that enters or leaves the drawer **outside a sale** is recorded as a
    ``cash_movements`` row tied to the shift (FIN-04 / POS-09): a ``pay_in`` adds to
    the drawer, a ``pay_out`` (petty cash / supplier paid from the till) and a
    ``cash_drop`` (skim to the safe) take from it. The drawer expectation folds them
    in: ``opening + cash_sales − cash_refunds + pay_in − pay_out − cash_drops``.

    This is the single source of truth shared by ``close_shift`` and the Z/X-report
    aggregator, so the printed report and the stored shift agree.

    Returns ``{cash_sales, cash_refunds, pay_in, pay_out, cash_drops,
    expected_cash}`` (all rounded to 2dp).
    """
    from models.cash_movements import Cash_movements
    from models.payment_tenders import PaymentTenders
    from models.transactions import Transactions

    txn_result = await db.execute(
        select(Transactions).where(Transactions.shift_id == shift.id)
    )
    transactions = txn_result.scalars().all()

    sale_ids: List[int] = []
    credit_note_ids: List[int] = []
    for t in transactions:
        status = t.status or "completed"
        if status == "credit_note":
            credit_note_ids.append(t.id)
        elif status == "voided":
            continue
        else:  # completed / refunded / partial_refunded — original sale rows
            sale_ids.append(t.id)

    # Real captured tenders for the sale rows, grouped per transaction.
    tenders_by_txn: Dict[int, list] = {}
    if sale_ids:
        tender_result = await db.execute(
            select(PaymentTenders).where(
                PaymentTenders.transaction_id.in_(sale_ids),
                PaymentTenders.status != "declined",
            )
        )
        for tr in tender_result.scalars().all():
            tenders_by_txn.setdefault(tr.transaction_id, []).append(tr)

    # Refund-to-origin tenders for the credit notes (F-004): only the cash leg of
    # a refund leaves the drawer; the card leg was reversed to the card.
    refund_tenders_by_txn: Dict[int, list] = {}
    if credit_note_ids:
        refund_result = await db.execute(
            select(PaymentTenders).where(
                PaymentTenders.transaction_id.in_(credit_note_ids),
                PaymentTenders.status == "refunded",
            )
        )
        for tr in refund_result.scalars().all():
            refund_tenders_by_txn.setdefault(tr.transaction_id, []).append(tr)

    cash_sales = 0.0
    for t in transactions:
        status = t.status or "completed"
        if status in ("credit_note", "voided"):
            continue
        rows = tenders_by_txn.get(t.id)
        if rows:
            for tr in rows:
                if (tr.tender_type or "") == "cash":
                    cash_sales += float(tr.amount or 0)
        elif (t.payment_method or "") == "cash":
            # Legacy sale without captured tenders: attribute its total to cash.
            cash_sales += float(t.total_amount or 0)

    cash_refunds = 0.0
    for t in transactions:
        if (t.status or "") != "credit_note":
            continue
        rows = refund_tenders_by_txn.get(t.id)
        if rows:
            for tr in rows:
                if (tr.tender_type or "") == "cash":
                    cash_refunds += float(tr.amount or 0)
        else:
            # Legacy credit note without recorded refund tenders: treat its full
            # total as cash paid out (pre-F-004 behavior).
            cash_refunds += abs(float(t.total_amount or 0))

    # Drawer movements outside a sale (FIN-04): pay-in adds to the drawer, pay-out
    # and cash-drop take from it. Tied to this shift, scoped to the shift owner.
    pay_in = 0.0
    pay_out = 0.0
    cash_drops = 0.0
    movement_result = await db.execute(
        select(Cash_movements).where(Cash_movements.shift_id == shift.id)
    )
    for m in movement_result.scalars().all():
        amount = abs(float(m.amount or 0))
        mtype = (m.movement_type or "").lower()
        if mtype == "pay_in":
            pay_in += amount
        elif mtype == "pay_out":
            pay_out += amount
        elif mtype == "cash_drop":
            cash_drops += amount

    cash_sales = round(cash_sales, 2)
    cash_refunds = round(cash_refunds, 2)
    pay_in = round(pay_in, 2)
    pay_out = round(pay_out, 2)
    cash_drops = round(cash_drops, 2)
    expected_cash = round(
        (shift.opening_cash or 0) + cash_sales - cash_refunds + pay_in - pay_out - cash_drops,
        2,
    )
    return {
        "cash_sales": cash_sales,
        "cash_refunds": cash_refunds,
        "pay_in": pay_in,
        "pay_out": pay_out,
        "cash_drops": cash_drops,
        "expected_cash": expected_cash,
    }