"""
Production-ready API router for the multi-tenant POS system.
Provides endpoints for permissions, health, metrics, invoicing,
notifications, stock alerts, webhooks, shifts, loyalty, bulk operations,
search, offline sync, analytics, branches, API usage, and sessions.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.auth import get_current_user
from dependencies.features import require_feature
from schemas.auth import UserResponse

# Imported at module level so ``Base.metadata.create_all`` registers the table on a
# fresh DB — the inter-branch transfer endpoint below only references it lazily (F-032).
from models.stock_transfers import Stock_transfers  # noqa: F401
from services.production import (
    AnalyticsService,
    BulkImportService,
    EmailService,
    LowStockChecker,
    OfflineSyncService,
    PDFInvoiceService,
    SearchService,
    WebhookDispatcher,
    compute_shift_cash_reconciliation,
    performance_monitor,
    rate_limiter,
    zatca_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/production", tags=["production"])


# =============================================================================
# Pydantic Schemas
# =============================================================================
class PermissionCheckRequest(BaseModel):
    permission_key: str
    target_user_id: Optional[str] = None


class PermissionGrantRequest(BaseModel):
    target_user_id: str
    role: str
    permission_key: str


class PermissionRevokeRequest(BaseModel):
    target_user_id: str
    permission_key: str


class InvoicePDFRequest(BaseModel):
    transaction_id: int


class ZATCAXMLRequest(BaseModel):
    transaction_id: int
    buyer_name: Optional[str] = "عميل"
    buyer_vat: Optional[str] = ""


class EmailNotificationRequest(BaseModel):
    to_email: str
    subject: str
    body: str
    html_body: Optional[str] = None


class WebhookTestRequest(BaseModel):
    webhook_id: int


class ShiftOpenRequest(BaseModel):
    opening_cash: float
    branch_id: Optional[int] = None
    staff_name: Optional[str] = None
    notes: Optional[str] = None


class ShiftCloseRequest(BaseModel):
    closing_cash: float
    notes: Optional[str] = None


class LoyaltyEarnRequest(BaseModel):
    customer_id: int
    transaction_amount: float
    points_rate: float = Field(default=1.0, description="Points per SAR spent")


class LoyaltyRedeemRequest(BaseModel):
    customer_id: int
    points_to_redeem: int
    redemption_value: float = Field(default=0.1, description="SAR value per point")


class BulkImportRequest(BaseModel):
    entity_type: str = Field(description="'products' or 'customers'")
    csv_content: str


class BulkExportRequest(BaseModel):
    entity_type: str = Field(description="'products', 'customers', or 'transactions'")


# Upper bound on a single offline-sync request (POS-12). The frontend flushes
# the IndexedDB backlog in bounded chunks (SYNC_CHUNK_SIZE), so a real client
# never approaches this; the guard is defence-in-depth against one giant payload
# (a legacy client or a long outage) overwhelming a single request.
MAX_OFFLINE_SYNC_BATCH = 500


class OfflineSyncRequest(BaseModel):
    transactions: List[Dict[str, Any]]


class SessionValidateRequest(BaseModel):
    pass  # Uses auth token from header


class SessionRefreshRequest(BaseModel):
    pass  # Uses auth token from header


# =============================================================================
# Permissions Endpoints
# =============================================================================
@router.post("/permissions/check")
async def check_permission(
    data: PermissionCheckRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check if the current user (or target user) has a specific permission."""
    from models.permissions import Permissions

    check_user_id = data.target_user_id or str(current_user.id)

    result = await db.execute(
        select(Permissions).where(
            Permissions.user_id == check_user_id,
            Permissions.permission_key == data.permission_key,
            Permissions.is_granted == True,  # noqa: E712
        )
    )
    permission = result.scalar_one_or_none()

    return {
        "user_id": check_user_id,
        "permission_key": data.permission_key,
        "is_granted": permission is not None,
        "role": permission.role if permission else None,
    }


@router.get("/permissions/list")
async def list_permissions(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all permissions for the current user."""
    from models.permissions import Permissions

    result = await db.execute(
        select(Permissions).where(
            Permissions.user_id == str(current_user.id),
            Permissions.is_granted == True,  # noqa: E712
        )
    )
    permissions = result.scalars().all()

    return {
        "user_id": str(current_user.id),
        "permissions": [
            {
                "id": p.id,
                "role": p.role,
                "permission_key": p.permission_key,
                "granted_by": p.granted_by,
            }
            for p in permissions
        ],
        "total": len(permissions),
    }


@router.post("/permissions/grant")
async def grant_permission(
    data: PermissionGrantRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Grant a permission to a user (master/agent only)."""
    from models.permissions import Permissions

    # Only master or agent roles can grant permissions
    if current_user.role not in ("admin", "master", "agent"):
        raise HTTPException(status_code=403, detail="Only master/agent can grant permissions")

    # Check if permission already exists
    existing = await db.execute(
        select(Permissions).where(
            Permissions.user_id == data.target_user_id,
            Permissions.permission_key == data.permission_key,
        )
    )
    perm = existing.scalar_one_or_none()

    if perm:
        # Update existing
        await db.execute(
            update(Permissions)
            .where(Permissions.id == perm.id)
            .values(is_granted=True, granted_by=str(current_user.id), role=data.role)
        )
    else:
        # Create new
        new_perm = Permissions(
            user_id=data.target_user_id,
            role=data.role,
            permission_key=data.permission_key,
            is_granted=True,
            granted_by=str(current_user.id),
        )
        db.add(new_perm)

    await db.commit()
    return {"status": "granted", "permission_key": data.permission_key, "target_user_id": data.target_user_id}


@router.post("/permissions/revoke")
async def revoke_permission(
    data: PermissionRevokeRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke a permission from a user."""
    from models.permissions import Permissions

    if current_user.role not in ("admin", "master", "agent"):
        raise HTTPException(status_code=403, detail="Only master/agent can revoke permissions")

    result = await db.execute(
        select(Permissions).where(
            Permissions.user_id == data.target_user_id,
            Permissions.permission_key == data.permission_key,
        )
    )
    perm = result.scalar_one_or_none()

    if not perm:
        raise HTTPException(status_code=404, detail="Permission not found")

    await db.execute(
        update(Permissions)
        .where(Permissions.id == perm.id)
        .values(is_granted=False)
    )
    await db.commit()

    return {"status": "revoked", "permission_key": data.permission_key, "target_user_id": data.target_user_id}


# =============================================================================
# Health & Metrics Endpoints
# =============================================================================
@router.get("/health/detailed")
async def detailed_health_check(
    db: AsyncSession = Depends(get_db),
):
    """Detailed health check with database and service status."""
    checks = {
        "database": "unknown",
        "rate_limiter": "healthy",
        "performance_monitor": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Check database
    try:
        await db.execute(select(func.now()))
        checks["database"] = "healthy"
    except Exception as e:
        checks["database"] = f"unhealthy: {str(e)}"

    overall = "healthy" if all(
        v == "healthy" for k, v in checks.items() if k != "timestamp"
    ) else "degraded"

    return {"status": overall, "checks": checks}


@router.get("/metrics")
async def get_metrics(
    current_user: UserResponse = Depends(get_current_user),
):
    """Get performance metrics (response times, request counts)."""
    if current_user.role not in ("admin", "master"):
        raise HTTPException(status_code=403, detail="Admin access required for metrics")

    return {
        "summary": performance_monitor.get_summary(),
        "endpoints": performance_monitor.get_metrics(),
        "rate_limiter": {
            "remaining_tokens": rate_limiter.get_remaining(str(current_user.id)),
        },
    }


# =============================================================================
# Invoice Endpoints
# =============================================================================
@router.post("/invoice/pdf")
async def generate_pdf_invoice(
    data: InvoicePDFRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate Arabic-only PDF invoice HTML from a transaction ID."""
    from models.clients import Clients
    from models.transactions import Transactions

    # Fetch transaction
    result = await db.execute(
        select(Transactions).where(
            Transactions.id == data.transaction_id,
            Transactions.user_id == str(current_user.id),
        )
    )
    txn = result.scalar_one_or_none()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    # Fetch client info for seller details
    client_result = await db.execute(
        select(Clients).where(Clients.id == txn.client_id)
    )
    client = client_result.scalar_one_or_none()

    seller_name = client.business_name if client else "متجر"
    seller_vat = client.vat_number if client else "000000000000000"

    # Parse items
    items = []
    if txn.items_json:
        try:
            items = json.loads(txn.items_json)
        except json.JSONDecodeError:
            items = []

    html = PDFInvoiceService.generate_invoice_html(
        seller_name=seller_name,
        seller_vat=seller_vat,
        buyer_name=txn.customer_name or "عميل",
        buyer_vat=txn.customer_vat_number or "",
        invoice_number=txn.invoice_number,
        issue_date=txn.created_at.strftime("%Y-%m-%d") if txn.created_at else "",
        line_items=items,
        subtotal=txn.subtotal or 0,
        vat_amount=txn.vat_amount or 0,
        total_amount=txn.total_amount or 0,
        zatca_qr=txn.zatca_qr or "",
        discount=txn.discount_amount or 0,
    )

    return {
        "invoice_number": txn.invoice_number,
        "html_content": html,
        "content_type": "text/html",
        "note": "Use a headless browser or wkhtmltopdf to convert HTML to PDF",
    }


@router.post("/invoice/zatca-xml")
async def generate_zatca_xml(
    data: ZATCAXMLRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate ZATCA Phase 2 compliant XML invoice."""
    from models.clients import Clients
    from models.transactions import Transactions

    result = await db.execute(
        select(Transactions).where(
            Transactions.id == data.transaction_id,
            Transactions.user_id == str(current_user.id),
        )
    )
    txn = result.scalar_one_or_none()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    client_result = await db.execute(
        select(Clients).where(Clients.id == txn.client_id)
    )
    client = client_result.scalar_one_or_none()

    seller_name = client.business_name if client else "متجر"
    seller_vat = client.vat_number if client else "000000000000000"

    items = []
    if txn.items_json:
        try:
            items = json.loads(txn.items_json)
        except json.JSONDecodeError:
            items = []

    issue_date = txn.created_at.strftime("%Y-%m-%d") if txn.created_at else datetime.now(timezone.utc).strftime("%Y-%m-%d")
    issue_time = txn.created_at.strftime("%H:%M:%S") if txn.created_at else datetime.now(timezone.utc).strftime("%H:%M:%S")

    xml_content = zatca_service.generate_xml_invoice(
        seller_name=seller_name,
        seller_vat=seller_vat,
        buyer_name=data.buyer_name or "عميل",
        buyer_vat=data.buyer_vat or "",
        invoice_number=txn.invoice_number,
        issue_date=issue_date,
        issue_time=issue_time,
        line_items=items,
        total_excluding_vat=txn.subtotal or 0,
        total_vat=txn.vat_amount or 0,
        total_including_vat=txn.total_amount or 0,
    )

    invoice_hash = zatca_service.generate_invoice_hash(xml_content.encode("utf-8"))

    return {
        "invoice_number": txn.invoice_number,
        "xml_content": xml_content,
        "invoice_hash": invoice_hash,
        "content_type": "application/xml",
        "zatca_phase": 2,
    }


# =============================================================================
# Notification Endpoints
# =============================================================================
@router.post("/notifications/send")
async def send_notification(
    data: EmailNotificationRequest,
    current_user: UserResponse = Depends(get_current_user),
):
    """Send an email notification."""
    result = await EmailService.send_email(
        to_email=data.to_email,
        subject=data.subject,
        body=data.body,
        html_body=data.html_body,
    )
    return result


# =============================================================================
# Stock Alerts
# =============================================================================
@router.get("/stock/alerts")
async def get_stock_alerts(
    threshold: int = Query(default=10, ge=0, description="Stock threshold"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get low stock alerts for current user's products."""
    alerts = await LowStockChecker.check_low_stock(
        db=db, user_id=str(current_user.id), threshold=threshold
    )
    return {
        "alerts": alerts,
        "total_alerts": len(alerts),
        "critical_count": sum(1 for a in alerts if a["severity"] == "critical"),
        "warning_count": sum(1 for a in alerts if a["severity"] == "warning"),
    }


# =============================================================================
# Webhook Endpoints
# =============================================================================
@router.post("/webhooks/test")
async def test_webhook(
    data: WebhookTestRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Test a webhook by sending a test event."""
    from models.webhooks import Webhooks

    result = await db.execute(
        select(Webhooks).where(
            Webhooks.id == data.webhook_id,
            Webhooks.user_id == str(current_user.id),
        )
    )
    webhook = result.scalar_one_or_none()
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    test_payload = {
        "event": "test.ping",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {"message": "This is a test webhook delivery"},
    }

    dispatch_result = await WebhookDispatcher.dispatch(
        url=webhook.url,
        event="test.ping",
        payload=test_payload,
        secret=webhook.secret_key or "default_secret",
    )

    return dispatch_result


# =============================================================================
# Shift Management Endpoints
# =============================================================================
@router.post("/shifts/open")
async def open_shift(
    data: ShiftOpenRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Open a new shift."""
    from models.shifts import Shifts

    # Check for existing open shift
    existing = await db.execute(
        select(Shifts).where(
            Shifts.user_id == str(current_user.id),
            Shifts.status == "open",
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="An open shift already exists. Close it first.")

    now = datetime.now(timezone.utc)
    shift = Shifts(
        user_id=str(current_user.id),
        branch_id=data.branch_id,
        staff_name=data.staff_name or current_user.name or current_user.email,
        start_time=now.isoformat(),
        opening_cash=data.opening_cash,
        status="open",
        notes=data.notes,
        total_sales=0,
        total_transactions=0,
    )
    db.add(shift)
    await db.commit()
    await db.refresh(shift)

    return {
        "id": shift.id,
        "status": "open",
        "start_time": shift.start_time,
        "opening_cash": shift.opening_cash,
        "staff_name": shift.staff_name,
    }


@router.post("/shifts/close")
async def close_shift(
    data: ShiftCloseRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Close the current open shift with cash reconciliation."""
    from models.shifts import Shifts

    result = await db.execute(
        select(Shifts).where(
            Shifts.user_id == str(current_user.id),
            Shifts.status == "open",
        )
    )
    shift = result.scalar_one_or_none()
    if not shift:
        raise HTTPException(status_code=404, detail="No open shift found")

    now = datetime.now(timezone.utc)
    # Reconcile the drawer against CASH tenders only — not gross sales (POS-09,
    # F-009). The shared helper is the single source of truth used by the
    # Z/X-report too, so the printed report and the stored shift always agree.
    recon = await compute_shift_cash_reconciliation(db, shift)
    expected_cash = recon["expected_cash"]
    cash_difference = round(data.closing_cash - expected_cash, 2)

    await db.execute(
        update(Shifts)
        .where(Shifts.id == shift.id)
        .values(
            end_time=now.isoformat(),
            closing_cash=data.closing_cash,
            expected_cash=expected_cash,
            cash_difference=cash_difference,
            status="closed",
            notes=data.notes or shift.notes,
        )
    )
    await db.commit()

    return {
        "id": shift.id,
        "status": "closed",
        "start_time": shift.start_time,
        "end_time": now.isoformat(),
        "opening_cash": shift.opening_cash,
        "closing_cash": data.closing_cash,
        "expected_cash": expected_cash,
        "cash_difference": cash_difference,
        "cash_sales": recon["cash_sales"],
        "cash_refunds": recon["cash_refunds"],
        "total_sales": shift.total_sales,
        "total_transactions": shift.total_transactions,
        "reconciliation": "balanced" if abs(cash_difference) < 0.01 else ("over" if cash_difference > 0 else "short"),
    }


@router.get("/shifts/current")
async def get_current_shift(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the current open shift."""
    from models.shifts import Shifts

    result = await db.execute(
        select(Shifts).where(
            Shifts.user_id == str(current_user.id),
            Shifts.status == "open",
        )
    )
    shift = result.scalar_one_or_none()

    if not shift:
        return {"status": "no_open_shift", "shift": None}

    return {
        "status": "open",
        "shift": {
            "id": shift.id,
            "start_time": shift.start_time,
            "opening_cash": shift.opening_cash,
            "total_sales": shift.total_sales,
            "total_transactions": shift.total_transactions,
            "staff_name": shift.staff_name,
            "branch_id": shift.branch_id,
            "notes": shift.notes,
        },
    }


@router.get("/shifts/history")
async def get_shift_history(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List the caller's closed shifts (most recent first) for reconciliation."""
    from models.shifts import Shifts

    result = await db.execute(
        select(Shifts)
        .where(Shifts.user_id == str(current_user.id), Shifts.status == "closed")
        .order_by(Shifts.id.desc())
        .limit(limit)
    )
    shifts = result.scalars().all()
    return {
        "shifts": [
            {
                "id": s.id,
                "staff_name": s.staff_name,
                "start_time": s.start_time,
                "end_time": s.end_time,
                "opening_cash": s.opening_cash,
                "closing_cash": s.closing_cash,
                "expected_cash": s.expected_cash,
                "cash_difference": s.cash_difference,
                "total_sales": s.total_sales,
                "total_transactions": s.total_transactions,
                "branch_id": s.branch_id,
                "notes": s.notes,
            }
            for s in shifts
        ],
        "total": len(shifts),
    }


# =============================================================================
# Loyalty Points Endpoints
# =============================================================================
@router.post("/loyalty/earn", dependencies=[Depends(require_feature("loyalty"))])
async def earn_loyalty_points(
    data: LoyaltyEarnRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Earn loyalty points from a transaction."""
    from models.loyalty_points import Loyalty_points

    points_earned = int(data.transaction_amount * data.points_rate)

    # Find or create loyalty record
    result = await db.execute(
        select(Loyalty_points).where(
            Loyalty_points.user_id == str(current_user.id),
            Loyalty_points.customer_id == data.customer_id,
        )
    )
    loyalty = result.scalar_one_or_none()

    if loyalty:
        new_balance = (loyalty.points_balance or 0) + points_earned
        new_total_earned = (loyalty.total_earned or 0) + points_earned
        await db.execute(
            update(Loyalty_points)
            .where(Loyalty_points.id == loyalty.id)
            .values(points_balance=new_balance, total_earned=new_total_earned)
        )
    else:
        new_loyalty = Loyalty_points(
            user_id=str(current_user.id),
            customer_id=data.customer_id,
            points_balance=points_earned,
            total_earned=points_earned,
            total_redeemed=0,
        )
        db.add(new_loyalty)

    await db.commit()

    return {
        "customer_id": data.customer_id,
        "points_earned": points_earned,
        "transaction_amount": data.transaction_amount,
        "new_balance": (loyalty.points_balance or 0) + points_earned if loyalty else points_earned,
    }


@router.post("/loyalty/redeem", dependencies=[Depends(require_feature("loyalty"))])
async def redeem_loyalty_points(
    data: LoyaltyRedeemRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Redeem loyalty points for a customer."""
    from models.loyalty_points import Loyalty_points

    result = await db.execute(
        select(Loyalty_points).where(
            Loyalty_points.user_id == str(current_user.id),
            Loyalty_points.customer_id == data.customer_id,
        )
    )
    loyalty = result.scalar_one_or_none()

    if not loyalty:
        raise HTTPException(status_code=404, detail="No loyalty record found for this customer")

    if (loyalty.points_balance or 0) < data.points_to_redeem:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient points. Available: {loyalty.points_balance}, Requested: {data.points_to_redeem}",
        )

    new_balance = (loyalty.points_balance or 0) - data.points_to_redeem
    new_total_redeemed = (loyalty.total_redeemed or 0) + data.points_to_redeem
    discount_value = data.points_to_redeem * data.redemption_value

    await db.execute(
        update(Loyalty_points)
        .where(Loyalty_points.id == loyalty.id)
        .values(points_balance=new_balance, total_redeemed=new_total_redeemed)
    )
    await db.commit()

    return {
        "customer_id": data.customer_id,
        "points_redeemed": data.points_to_redeem,
        "discount_value": round(discount_value, 2),
        "remaining_balance": new_balance,
    }


@router.get("/loyalty/balance")
async def get_loyalty_balance(
    customer_id: int = Query(..., description="Customer ID"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get customer loyalty points balance."""
    from models.loyalty_points import Loyalty_points

    result = await db.execute(
        select(Loyalty_points).where(
            Loyalty_points.user_id == str(current_user.id),
            Loyalty_points.customer_id == customer_id,
        )
    )
    loyalty = result.scalar_one_or_none()

    if not loyalty:
        return {
            "customer_id": customer_id,
            "points_balance": 0,
            "total_earned": 0,
            "total_redeemed": 0,
        }

    return {
        "customer_id": customer_id,
        "points_balance": loyalty.points_balance or 0,
        "total_earned": loyalty.total_earned or 0,
        "total_redeemed": loyalty.total_redeemed or 0,
    }


# =============================================================================
# Bulk Import/Export Endpoints
# =============================================================================
@router.post("/bulk/import")
async def bulk_import(
    data: BulkImportRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Import CSV data for products or customers."""
    rows = BulkImportService.parse_csv(data.csv_content)

    if not rows:
        raise HTTPException(status_code=400, detail="No valid rows found in CSV")

    if data.entity_type == "products":
        validation = BulkImportService.validate_product_rows(rows)
        if validation["valid_count"] > 0:
            from models.products import Products

            imported = 0
            for row in validation["valid_rows"]:
                product = Products(
                    user_id=str(current_user.id),
                    name=row.get("name", ""),
                    name_ar=row.get("name_ar", ""),
                    barcode=row.get("barcode", ""),
                    price=float(row.get("price", 0)),
                    cost_price=float(row.get("cost_price", 0)) if row.get("cost_price") else None,
                    quantity=int(row.get("quantity", 0)) if row.get("quantity") else 0,
                    category=row.get("category", ""),
                    vat_rate=float(row.get("vat_rate", 15)),
                    is_active=True,
                )
                db.add(product)
                imported += 1
            await db.commit()
            validation["imported"] = imported

    elif data.entity_type == "customers":
        validation = BulkImportService.validate_customer_rows(rows)
        if validation["valid_count"] > 0:
            from models.customers import Customers

            imported = 0
            for row in validation["valid_rows"]:
                customer = Customers(
                    user_id=str(current_user.id),
                    name=row.get("name", ""),
                    phone=row.get("phone", ""),
                    email=row.get("email", ""),
                    notes=row.get("notes", ""),
                )
                db.add(customer)
                imported += 1
            await db.commit()
            validation["imported"] = imported
    else:
        raise HTTPException(status_code=400, detail="entity_type must be 'products' or 'customers'")

    # Remove raw rows from response to keep it clean
    validation.pop("valid_rows", None)
    return validation


@router.post("/bulk/export")
async def bulk_export(
    data: BulkExportRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export data as CSV."""
    user_id = str(current_user.id)

    if data.entity_type == "products":
        from models.products import Products

        result = await db.execute(
            select(Products).where(Products.user_id == user_id)
        )
        items = result.scalars().all()
        export_data = [
            {
                "id": p.id,
                "name": p.name,
                "name_ar": p.name_ar,
                "barcode": p.barcode,
                "price": p.price,
                "cost_price": p.cost_price,
                "quantity": p.quantity,
                "category": p.category,
                "vat_rate": p.vat_rate,
                "is_active": p.is_active,
            }
            for p in items
        ]

    elif data.entity_type == "customers":
        from models.customers import Customers

        result = await db.execute(
            select(Customers).where(Customers.user_id == user_id)
        )
        items = result.scalars().all()
        export_data = [
            {
                "id": c.id,
                "name": c.name,
                "phone": c.phone,
                "email": c.email,
                "notes": c.notes,
                "total_purchases": c.total_purchases,
                "visit_count": c.visit_count,
            }
            for c in items
        ]

    elif data.entity_type == "transactions":
        from models.transactions import Transactions

        result = await db.execute(
            select(Transactions).where(Transactions.user_id == user_id)
        )
        items = result.scalars().all()
        export_data = [
            {
                "id": t.id,
                "invoice_number": t.invoice_number,
                "subtotal": t.subtotal,
                "vat_amount": t.vat_amount,
                "discount_amount": t.discount_amount,
                "total_amount": t.total_amount,
                "payment_method": t.payment_method,
                "status": t.status,
                "customer_name": t.customer_name,
                "created_at": t.created_at.isoformat() if t.created_at else "",
            }
            for t in items
        ]
    else:
        raise HTTPException(status_code=400, detail="entity_type must be 'products', 'customers', or 'transactions'")

    csv_content = BulkImportService.generate_csv_export(export_data)

    return {
        "entity_type": data.entity_type,
        "total_records": len(export_data),
        "csv_content": csv_content,
        "content_type": "text/csv",
    }


# =============================================================================
# Search Endpoint
# =============================================================================
@router.get("/search")
async def global_search(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Global search across products, customers, and transactions."""
    results = await SearchService.global_search(
        db=db, user_id=str(current_user.id), query=q, limit=limit
    )

    total_results = sum(len(v) for v in results.values())
    return {
        "query": q,
        "total_results": total_results,
        "results": results,
    }


# =============================================================================
# Offline Sync Endpoint
# =============================================================================
@router.post("/offline/sync")
async def sync_offline_transactions(
    data: OfflineSyncRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Sync offline-queued transactions through the full atomic sale path (POS-05)."""
    if not data.transactions:
        raise HTTPException(status_code=400, detail="No transactions to sync")
    if len(data.transactions) > MAX_OFFLINE_SYNC_BATCH:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Too many transactions in one sync ({len(data.transactions)}); "
                f"send at most {MAX_OFFLINE_SYNC_BATCH} per request (POS-12)."
            ),
        )

    from routers.pos import get_client_for_user

    client = await get_client_for_user(db, str(current_user.id))
    result = await OfflineSyncService.process_offline_queue(
        db=db,
        user_id=str(current_user.id),
        client_id=client.id,
        queued_transactions=data.transactions,
    )
    return result


# =============================================================================
# Analytics Endpoint
# =============================================================================
@router.get("/analytics/forecast")
async def get_sales_forecast(
    days: int = Query(default=30, ge=1, le=90, description="Days to forecast"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """AI-powered sales forecast."""
    forecast = await AnalyticsService.get_sales_forecast(
        db=db, user_id=str(current_user.id), days_ahead=days
    )
    return forecast


# =============================================================================
# Multi-Branch Inventory
# =============================================================================
@router.get("/branches/inventory")
async def get_branch_inventory(
    branch_id: Optional[int] = Query(default=None, description="Filter by branch ID"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get multi-branch inventory view backed by the per-branch stock ledger.

    Each branch reports its *own* quantities from ``product_branch_stock``;
    products with no ledger row for a branch fall back to the client-level
    ``products.quantity`` (the aggregate/opening stock). This replaces the former
    façade that showed identical client-level stock for every branch.
    """
    from models.branches import Branches
    from models.product_branch_stock import Product_branch_stock
    from models.products import Products

    # Get branches for user
    branch_query = select(Branches).where(Branches.user_id == str(current_user.id))
    if branch_id:
        branch_query = branch_query.where(Branches.id == branch_id)

    branch_result = await db.execute(branch_query)
    branches = branch_result.scalars().all()

    # Get all products for user
    prod_result = await db.execute(
        select(Products).where(
            Products.user_id == str(current_user.id),
            Products.is_active == True,  # noqa: E712
        )
    )
    products = prod_result.scalars().all()

    # Per-branch ledger overrides, keyed by (branch_id, product_id).
    ledger_result = await db.execute(
        select(Product_branch_stock).where(
            Product_branch_stock.user_id == str(current_user.id)
        )
    )
    ledger = {(r.branch_id, r.product_id): r.quantity for r in ledger_result.scalars().all()}

    # Build inventory view
    inventory = []
    for branch in branches:
        def _qty(p):
            return ledger.get((branch.id, p.id), p.quantity or 0)

        branch_data = {
            "branch_id": branch.id,
            "branch_name": branch.name,
            "city": branch.city,
            "is_main": branch.is_main,
            "total_products": len(products),
            "total_stock_value": sum((p.price or 0) * _qty(p) for p in products),
            "low_stock_count": sum(1 for p in products if _qty(p) <= 10),
            "out_of_stock_count": sum(1 for p in products if _qty(p) <= 0),
        }
        inventory.append(branch_data)

    return {
        "branches": inventory,
        "total_branches": len(inventory),
        "total_products": len(products),
    }


class StockTransferRequest(BaseModel):
    from_branch_id: int
    to_branch_id: int
    # Either a product_id (preferred) or a product_name (resolved within the client).
    product_id: Optional[int] = None
    product_name: Optional[str] = None
    quantity: int


@router.post("/branches/transfer")
async def transfer_branch_stock(
    data: StockTransferRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Move stock between two branches on the per-branch ledger (INV-05, F-032).

    Decrements the source branch and increments the destination branch atomically on
    ``product_branch_stock`` (the ledger the POS deducts from), then writes a
    ``stock_transfers`` audit row. This wires up the Branch Management "Transfer
    Stock" dialog, which previously POSTed to a route that did not exist (404 — a
    dead-end UI). Owner-scoped: both branches and the product must belong to the
    caller's client (SEC-02). Insufficient source stock → 400.
    """
    from models.branches import Branches
    from models.clients import Clients
    from models.products import Products
    from models.stock_transfers import Stock_transfers as StockTransfers
    from services.branch_stock import get_or_init_row

    logger.debug("[TRANSFER] user=%s from=%s to=%s qty=%s", current_user.id, data.from_branch_id, data.to_branch_id, data.quantity)

    # POS features are client-scoped — resolve the caller's client row.
    client = (
        await db.execute(select(Clients).where(Clients.user_id == str(current_user.id)))
    ).scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=403, detail="Only clients can transfer stock")

    qty = int(data.quantity or 0)
    if qty <= 0:
        raise HTTPException(status_code=400, detail="Transfer quantity must be positive")
    if int(data.from_branch_id) == int(data.to_branch_id):
        raise HTTPException(status_code=400, detail="Source and destination branches must differ")

    # Both branches must belong to the caller (owner-scoped — SEC-02).
    branch_rows = (
        await db.execute(
            select(Branches).where(
                Branches.user_id == str(current_user.id),
                Branches.id.in_([int(data.from_branch_id), int(data.to_branch_id)]),
            )
        )
    ).scalars().all()
    found_ids = {b.id for b in branch_rows}
    if int(data.from_branch_id) not in found_ids or int(data.to_branch_id) not in found_ids:
        raise HTTPException(status_code=404, detail="Branch not found")

    # Resolve the product within the caller's client scope (by id, else by exact name).
    prod_query = select(Products).where(Products.client_id == client.id)
    if data.product_id is not None:
        prod_query = prod_query.where(Products.id == int(data.product_id))
    elif (data.product_name or "").strip():
        prod_query = prod_query.where(Products.name == data.product_name.strip())
    else:
        raise HTTPException(status_code=400, detail="A product_id or product_name is required")
    product = (await db.execute(prod_query)).scalars().first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Move stock on the per-branch ledger (source−, dest+), seeding ledger rows the
    # same way the sale path does. The helpers do not commit — we commit once below
    # so the two legs + the audit row land atomically (roll back wholly on any raise).
    src = await get_or_init_row(
        db, str(current_user.id), client.id, int(data.from_branch_id), product
    )
    if (src.quantity or 0) < qty:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Insufficient stock for '{product.name}' at the source branch: "
                f"requested {qty}, available {src.quantity or 0}"
            ),
        )
    dst = await get_or_init_row(
        db, str(current_user.id), client.id, int(data.to_branch_id), product
    )
    src.quantity = (src.quantity or 0) - qty
    dst.quantity = (dst.quantity or 0) + qty

    record = StockTransfers(
        user_id=str(current_user.id),
        client_id=client.id,
        from_branch_id=int(data.from_branch_id),
        to_branch_id=int(data.to_branch_id),
        product_id=product.id,
        product_name=product.name,
        quantity=qty,
        status="received",
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    return {
        "id": record.id,
        "from_branch_id": record.from_branch_id,
        "to_branch_id": record.to_branch_id,
        "product_id": record.product_id,
        "product_name": record.product_name,
        "quantity": record.quantity,
        "status": record.status,
        "from_branch_quantity": src.quantity,
        "to_branch_quantity": dst.quantity,
    }


# =============================================================================
# API Usage Stats
# =============================================================================
@router.get("/api-usage/stats")
async def get_api_usage_stats(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get API usage statistics for rate plans."""
    from models.api_usage import Api_usage

    result = await db.execute(
        select(
            Api_usage.endpoint,
            func.count(Api_usage.id).label("request_count"),
            func.avg(Api_usage.response_time_ms).label("avg_response_time"),
        )
        .where(Api_usage.user_id == str(current_user.id))
        .group_by(Api_usage.endpoint)
    )
    stats = result.all()

    total_result = await db.execute(
        select(func.count(Api_usage.id)).where(
            Api_usage.user_id == str(current_user.id)
        )
    )
    total_requests = total_result.scalar() or 0

    return {
        "user_id": str(current_user.id),
        "total_requests": total_requests,
        "endpoints": [
            {
                "endpoint": s.endpoint,
                "request_count": s.request_count,
                "avg_response_time_ms": round(float(s.avg_response_time or 0), 2),
            }
            for s in stats
        ],
        "rate_limit": {
            "remaining_tokens": rate_limiter.get_remaining(str(current_user.id)),
            "max_tokens": rate_limiter.max_tokens,
            "refill_rate_per_second": rate_limiter.refill_rate,
        },
    }


# =============================================================================
# Session Management
# =============================================================================
@router.post("/session/validate")
async def validate_session(
    current_user: UserResponse = Depends(get_current_user),
):
    """Validate the current session token."""
    return {
        "valid": True,
        "user_id": str(current_user.id),
        "email": current_user.email,
        "role": current_user.role,
        "name": current_user.name,
        "last_login": current_user.last_login.isoformat() if current_user.last_login else None,
    }


@router.post("/session/refresh")
async def refresh_session(
    current_user: UserResponse = Depends(get_current_user),
):
    """
    Refresh the current session.
    In production, this would issue a new token with extended expiry.
    Currently validates the existing token and returns session info.
    """
    return {
        "status": "refreshed",
        "user_id": str(current_user.id),
        "email": current_user.email,
        "role": current_user.role,
        "note": "Token refresh is handled by the auth system. This endpoint validates the current session.",
    }