"""
Production services module for the multi-tenant POS system.
Contains rate limiting, performance monitoring, ZATCA Phase 2,
PDF invoice generation, email, webhooks, low stock alerts,
bulk import/export, search, analytics, and offline sync services.
"""

import base64
import csv
import hashlib
import hmac
import io
import json
import logging
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from xml.etree.ElementTree import Element, SubElement, tostring

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


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
    """ZATCA Phase 2 compliant XML invoice generation with cryptographic stamp."""

    ZATCA_NS = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
    CAC_NS = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
    CBC_NS = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"

    def __init__(self):
        self._invoice_counter: int = 0
        self._previous_hash: str = "0" * 64  # Initial hash for chain

    def _next_sequential_number(self) -> str:
        """Generate sequential invoice number for ZATCA compliance."""
        self._invoice_counter += 1
        return f"ZATCA-{self._invoice_counter:010d}"

    def generate_invoice_hash(self, xml_content: bytes) -> str:
        """Generate SHA-256 hash of invoice XML."""
        return hashlib.sha256(xml_content).hexdigest()

    def generate_cryptographic_stamp(
        self, invoice_hash: str, private_key_pem: Optional[str] = None
    ) -> str:
        """Generate the cryptographic stamp for an invoice hash.

        Phase B: when a per-client EGS ``private_key_pem`` is supplied (see
        ``services/zatca.py`` and ``routers/zatca.py``), this produces a **real**
        ECDSA-SHA256 signature over the hash — the compliant ZATCA stamp.

        ``invoice_hash`` may be a hex SHA-256 (legacy ``generate_invoice_hash``)
        or a base64 SHA-256 digest; both are normalised to the base64 digest the
        signer expects.

        With no key (legacy/dev callers) it falls back to an HMAC tag that is
        **NOT ZATCA-valid** — kept only so existing demo flows don't break.
        """
        digest_b64 = self._normalise_hash_to_b64_digest(invoice_hash)
        if private_key_pem:
            from services.zatca import sign_invoice_hash

            return sign_invoice_hash(private_key_pem, digest_b64)

        # Non-compliant dev fallback (no EGS key onboarded yet).
        stamp_key = b"ZATCA_DEV_FALLBACK_UNSIGNED"
        signature = hmac.new(stamp_key, digest_b64.encode(), hashlib.sha256).hexdigest()
        return base64.b64encode(signature.encode()).decode()

    @staticmethod
    def _normalise_hash_to_b64_digest(invoice_hash: str) -> str:
        """Return the base64 of the 32-byte SHA-256 digest.

        Accepts a 64-char hex digest (from ``generate_invoice_hash``) or an
        already-base64-encoded digest.
        """
        try:
            if len(invoice_hash) == 64:
                int(invoice_hash, 16)  # validate hex
                return base64.b64encode(bytes.fromhex(invoice_hash)).decode()
        except ValueError:
            pass
        return invoice_hash

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
    ) -> str:
        """Generate ZATCA Phase 2 compliant UBL 2.1 XML invoice."""
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

        # UUID
        inv_uuid = SubElement(invoice, "cbc:UUID")
        inv_uuid.text = str(uuid.uuid4())

        # Issue Date & Time
        issue_date_el = SubElement(invoice, "cbc:IssueDate")
        issue_date_el.text = issue_date
        issue_time_el = SubElement(invoice, "cbc:IssueTime")
        issue_time_el.text = issue_time

        # Invoice Type Code (388 = Tax Invoice)
        type_code = SubElement(invoice, "cbc:InvoiceTypeCode")
        type_code.text = "388"
        type_code.set("name", "0100000")

        # Document Currency
        currency = SubElement(invoice, "cbc:DocumentCurrencyCode")
        currency.text = "SAR"

        # Previous Invoice Hash (for chaining)
        additional_doc = SubElement(invoice, "cac:AdditionalDocumentReference")
        doc_id = SubElement(additional_doc, "cbc:ID")
        doc_id.text = "PIH"
        attachment = SubElement(additional_doc, "cac:Attachment")
        embedded = SubElement(attachment, "cbc:EmbeddedDocumentBinaryObject")
        embedded.set("mimeCode", "text/plain")
        embedded.text = self._previous_hash

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
        cat_id = SubElement(tax_category, "cbc:ID")
        cat_id.text = "S"
        percent = SubElement(tax_category, "cbc:Percent")
        percent.text = "15.00"
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

        # Update hash chain
        invoice_hash = self.generate_invoice_hash(full_xml.encode("utf-8"))
        self._previous_hash = invoice_hash

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
    ) -> str:
        """Generate Arabic-only HTML invoice suitable for PDF conversion."""
        items_html = ""
        for idx, item in enumerate(line_items, 1):
            item_total = item.get("price", 0) * item.get("quantity", 1)
            items_html += f"""
            <tr>
                <td>{idx}</td>
                <td>{item.get('name', '')}</td>
                <td>{item.get('quantity', 1)}</td>
                <td>{item.get('price', 0):.2f} ر.س</td>
                <td>{item_total:.2f} ر.س</td>
            </tr>"""

        html = f"""<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: 'Noto Sans Arabic', 'Arial', sans-serif; direction: rtl; padding: 20px; }}
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
        </div>
    </div>

    <div>
        <p><strong>رقم الفاتورة:</strong> {invoice_number}</p>
        <p><strong>التاريخ:</strong> {issue_date}</p>
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
            <tr><td>المجموع الفرعي</td><td>{subtotal:.2f} ر.س</td></tr>
            <tr><td>الخصم</td><td>{discount:.2f} ر.س</td></tr>
            <tr><td>ضريبة القيمة المضافة (15%)</td><td>{vat_amount:.2f} ر.س</td></tr>
            <tr><td><strong>الإجمالي</strong></td><td><strong>{total_amount:.2f} ر.س</strong></td></tr>
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


# =============================================================================
# Email Service (Stub with Logging)
# =============================================================================
class EmailService:
    """Email notification service (stub implementation with logging)."""

    @staticmethod
    async def send_email(
        to_email: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send an email notification (logged, not actually sent in stub mode)."""
        message_id = str(uuid.uuid4())
        logger.info(
            "EMAIL_SEND",
            extra={
                "message_id": message_id,
                "to": to_email,
                "subject": subject,
                "body_length": len(body),
                "has_html": html_body is not None,
            },
        )
        return {
            "message_id": message_id,
            "status": "queued",
            "to": to_email,
            "subject": subject,
            "note": "Email service is in stub mode. Configure SMTP for production.",
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
        body = f"رقم الفاتورة: {invoice_number}\nالإجمالي: {total:.2f} ر.س"
        return await EmailService.send_email(to_email, subject, body)


# =============================================================================
# Webhook Dispatcher
# =============================================================================
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

    @staticmethod
    async def dispatch(
        url: str,
        event: str,
        payload: Dict[str, Any],
        secret: str,
    ) -> Dict[str, Any]:
        """
        Dispatch a webhook event.
        In production, this would use httpx/aiohttp to POST to the URL.
        Currently logs the dispatch for stub mode.
        """
        payload_str = json.dumps(payload, ensure_ascii=False, default=str)
        signature = WebhookDispatcher.generate_signature(payload_str, secret)
        delivery_id = str(uuid.uuid4())

        logger.info(
            "WEBHOOK_DISPATCH",
            extra={
                "delivery_id": delivery_id,
                "url": url,
                "event": event,
                "signature": signature[:16] + "...",
                "payload_size": len(payload_str),
            },
        )

        return {
            "delivery_id": delivery_id,
            "url": url,
            "event": event,
            "status": "dispatched",
            "signature": f"sha256={signature}",
            "note": "Webhook dispatcher is in stub mode. Configure HTTP client for production.",
        }


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
# Analytics Service (AI Forecasting Stub)
# =============================================================================
class AnalyticsService:
    """Advanced analytics with AI-powered sales forecasting (stub)."""

    @staticmethod
    async def get_sales_forecast(
        db: AsyncSession, user_id: str, days_ahead: int = 30
    ) -> Dict[str, Any]:
        """
        Generate sales forecast.
        In production, this would use ML models trained on historical data.
        Currently returns a simple moving average projection.
        """
        from models.transactions import Transactions

        # Get recent transaction totals
        result = await db.execute(
            select(
                func.date(Transactions.created_at).label("sale_date"),
                func.sum(Transactions.total_amount).label("daily_total"),
                func.count(Transactions.id).label("transaction_count"),
            )
            .where(Transactions.user_id == user_id)
            .group_by(func.date(Transactions.created_at))
            .order_by(func.date(Transactions.created_at).desc())
            .limit(30)
        )
        daily_sales = result.all()

        if not daily_sales:
            return {
                "forecast": [],
                "avg_daily_sales": 0,
                "trend": "insufficient_data",
                "confidence": 0,
            }

        totals = [float(row.daily_total) for row in daily_sales if row.daily_total]
        avg_daily = sum(totals) / len(totals) if totals else 0

        # Simple trend detection
        if len(totals) >= 7:
            recent_avg = sum(totals[:7]) / 7
            older_avg = sum(totals[7:14]) / max(len(totals[7:14]), 1)
            if recent_avg > older_avg * 1.1:
                trend = "growing"
            elif recent_avg < older_avg * 0.9:
                trend = "declining"
            else:
                trend = "stable"
        else:
            trend = "insufficient_data"

        # Generate forecast (simple projection)
        forecast = []
        now = datetime.now(timezone.utc)
        for i in range(1, days_ahead + 1):
            forecast_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            forecast.append({
                "day": i,
                "projected_sales": round(avg_daily * (1.02 if trend == "growing" else 0.98 if trend == "declining" else 1.0) ** i, 2),
            })

        return {
            "forecast": forecast[:days_ahead],
            "avg_daily_sales": round(avg_daily, 2),
            "trend": trend,
            "confidence": min(len(totals) / 30 * 100, 100),
            "data_points": len(totals),
            "note": "AI forecasting is in stub mode. Integrate ML model for production.",
        }


# =============================================================================
# Offline Sync Service
# =============================================================================
class OfflineSyncService:
    """Processes queued offline transactions when device reconnects."""

    @staticmethod
    async def process_offline_queue(
        db: AsyncSession,
        user_id: str,
        queued_transactions: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Process a batch of offline-queued transactions.
        Validates, deduplicates, and persists them.
        """
        from models.transactions import Transactions

        processed = 0
        skipped = 0
        errors = []

        for idx, txn in enumerate(queued_transactions):
            try:
                # Check for duplicate by offline_id if provided
                offline_id = txn.get("offline_id")
                if offline_id:
                    existing = await db.execute(
                        select(Transactions).where(
                            Transactions.user_id == user_id,
                            Transactions.invoice_number == offline_id,
                        )
                    )
                    if existing.scalar_one_or_none():
                        skipped += 1
                        continue

                # Create transaction record
                transaction = Transactions(
                    user_id=user_id,
                    client_id=txn.get("client_id"),
                    invoice_number=offline_id or f"OFFLINE-{uuid.uuid4().hex[:8].upper()}",
                    subtotal=txn.get("subtotal", 0),
                    vat_amount=txn.get("vat_amount", 0),
                    discount_amount=txn.get("discount_amount", 0),
                    total_amount=txn.get("total_amount", 0),
                    payment_method=txn.get("payment_method", "cash"),
                    status="completed",
                    items_json=json.dumps(txn.get("items", []), ensure_ascii=False),
                    customer_name=txn.get("customer_name"),
                    customer_phone=txn.get("customer_phone"),
                )
                db.add(transaction)
                processed += 1

            except Exception as e:
                errors.append({"index": idx, "error": str(e)})

        if processed > 0:
            await db.commit()

        return {
            "processed": processed,
            "skipped_duplicates": skipped,
            "errors": errors,
            "total_submitted": len(queued_transactions),
        }