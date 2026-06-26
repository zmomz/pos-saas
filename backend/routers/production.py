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

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.auth import get_current_user
from dependencies.tenancy import TenantScope, get_owner_id, get_tenant_scope
from dependencies.features import require_feature
from schemas.auth import UserResponse

# Imported at module level so ``Base.metadata.create_all`` registers the table on a
# fresh DB — the inter-branch transfer endpoint below only references it lazily (F-032).
from models.stock_transfers import Stock_transfers  # noqa: F401
# Imported so the stock_adjustments table registers on Base.metadata at startup
# (INV-06 / F-036 counts & adjustments).
from models.stock_adjustments import Stock_adjustments  # noqa: F401
# Imported so the cash_movements table registers on Base.metadata at startup
# (FIN-04 / POS-09 / F-044 drawer pay-in/pay-out/cash-drop tied to the shift).
from models.cash_movements import Cash_movements  # noqa: F401
# Imported so the shifts table registers on Base.metadata at startup. The shift
# open/close/reconciliation endpoints below reference it lazily; the deleted
# entities/shifts CRUD scaffold (H20, #5) used to be its only startup importer.
from models.shifts import Shifts  # noqa: F401
# Imported so the loyalty_transactions ledger table registers on Base.metadata at
# startup (ISSUE-028 / C4). The loyalty admin endpoints below reference it lazily.
from models.loyalty_transactions import Loyalty_transactions  # noqa: F401
# Imported so the webhook_deliveries log table registers on Base.metadata at
# startup (ISSUE-029 / H24). The /webhooks/logs endpoint references it lazily.
from models.webhook_deliveries import Webhook_deliveries  # noqa: F401
from models.customers import Customers  # noqa: F401
from services.production import (
    BulkImportService,
    EmailService,
    LowStockChecker,
    OfflineSyncService,
    PDFInvoiceService,
    SearchService,
    WebhookDispatcher,
    compute_shift_cash_reconciliation,
    fire_event_background,
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
    permission_key: str
    # Deprecated/ignored: role no longer lives on a per-user override row — the
    # role→permission defaults are in dependencies.permissions.ROLE_PERMISSIONS
    # (ISSUE-034). Accepted for backward compatibility, never persisted.
    role: Optional[str] = None


class PermissionRevokeRequest(BaseModel):
    target_user_id: str
    permission_key: str


class StaffPermissionSetRequest(BaseModel):
    """Set a per-staff override on a managed key. ``is_granted=None`` resets the
    override (deletes the row) so the key falls back to the staff role default."""
    permission_key: str
    is_granted: Optional[bool] = None


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


class CashMovementRequest(BaseModel):
    # FIN-04 / POS-09 drawer movement against the open shift. ``amount`` is the
    # positive cash magnitude; the sign is implied by ``movement_type``.
    movement_type: str = Field(description="pay_in | pay_out | cash_drop")
    amount: float = Field(gt=0, description="Positive cash magnitude")
    reason: Optional[str] = None


class LoyaltyEarnRequest(BaseModel):
    customer_id: int
    transaction_amount: float
    points_rate: float = Field(default=1.0, description="Points per SAR spent")


# FIN-05: platform fallback per-point redemption value (SAR) used by the
# standalone redeem endpoint when the merchant has no active program configured.
# Matches the historical request-field default so existing callers are unchanged.
DEFAULT_REDEMPTION_RATE = 0.1


class LoyaltyRedeemRequest(BaseModel):
    customer_id: int
    points_to_redeem: int
    # FIN-05: the per-point value is derived server-side from the merchant's
    # active loyalty program (or DEFAULT_REDEMPTION_RATE when none is
    # configured) — never from the client, which previously let a caller value a
    # point arbitrarily high. ``order_subtotal`` is an optional cap so the
    # discount can never exceed what is actually being paid, mirroring the atomic
    # POS redemption path (services/loyalty.redeem_points).
    order_subtotal: Optional[float] = Field(
        default=None, ge=0, description="Order subtotal to cap the discount at"
    )


class LoyaltyConfigRequest(BaseModel):
    """Loyalty-program settings as the admin page (LoyaltyProgram.tsx) models them.

    ``min_points_redeem`` is the page's name for the model's
    ``min_redemption_points`` — reconciled in the endpoint.
    """

    points_per_sar: float = Field(default=1.0, ge=0)
    redemption_rate: float = Field(default=0.1, ge=0)
    min_points_redeem: int = Field(default=100, ge=0)
    # Points expire this many days after being earned; 0 = never (ISSUE-044).
    points_expiry_days: int = Field(default=0, ge=0)
    is_active: bool = True


class LoyaltyAdjustRequest(BaseModel):
    customer_id: int
    type: str = Field(description="'add' or 'deduct'")
    points: int = Field(ge=0)
    reason: Optional[str] = None


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
    """Check if the current user (or target user) has a specific permission.

    Delegates to the canonical resolver so the answer reflects both explicit
    overrides and the staff role→permission defaults (ISSUE-034), not just the
    presence of an explicit grant row.
    """
    from dependencies.permissions import has_permission

    check_user_id = data.target_user_id or str(current_user.id)

    granted = await has_permission(db, check_user_id, data.permission_key)

    return {
        "user_id": check_user_id,
        "permission_key": data.permission_key,
        "is_granted": granted,
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
            .values(is_granted=True, granted_by=str(current_user.id))
        )
    else:
        # Create new
        new_perm = Permissions(
            user_id=data.target_user_id,
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


# -----------------------------------------------------------------------------
# Staff-permission editor (ISSUE-035, H12) — owner-scoped override of role defaults
# -----------------------------------------------------------------------------
async def _resolve_owned_staff_login(
    db: AsyncSession, owner_user_id: Optional[str], staff_member_id: int
):
    """Return ``(staff_row, login_user_id)`` for a staff member the caller owns.

    Owner-scoped: the staff row must belong to ``owner_user_id`` (the tenancy
    owner), otherwise a cross-tenant edit is rejected with 404. ``login_user_id``
    is the staff member's *auth* account (resolved by email — the same key
    ``has_permission`` checks), or ``None`` when the staff entry has no login.
    """
    from models.auth import User
    from models.staff_members import Staff_members

    staff = (
        await db.execute(
            select(Staff_members).where(
                Staff_members.id == staff_member_id,
                Staff_members.user_id == str(owner_user_id),
            )
        )
    ).scalar_one_or_none()
    if staff is None:
        raise HTTPException(status_code=404, detail="Staff member not found")

    login_uid = None
    if staff.email:
        login_uid = (
            await db.execute(select(User.id).where(User.email == staff.email))
        ).scalars().first()
    return staff, (str(login_uid) if login_uid else None)


def _effective_permission_map(role: str, overrides: dict) -> list[dict]:
    """The managed-key map for a staff ``role`` layered with explicit ``overrides``."""
    from dependencies.permissions import MANAGED_PERMISSION_KEYS, role_allows

    rows = []
    for key in sorted(MANAGED_PERMISSION_KEYS):
        default = role_allows(role, key)
        override = overrides.get(key)  # True / False / None (no override row)
        rows.append(
            {
                "permission_key": key,
                "role_default": default,
                "override": override,
                "effective": override if override is not None else default,
            }
        )
    return rows


@router.get("/staff-permissions/{staff_member_id}")
async def get_staff_permissions(
    staff_member_id: int,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """The effective managed-permission map for one of the owner's staff members."""
    from models.permissions import Permissions

    staff, login_uid = await _resolve_owned_staff_login(
        db, scope.owner_user_id, staff_member_id
    )

    overrides: dict = {}
    if login_uid:
        rows = (
            await db.execute(
                select(Permissions.permission_key, Permissions.is_granted).where(
                    Permissions.user_id == login_uid
                )
            )
        ).all()
        overrides = {key: is_granted for key, is_granted in rows}

    return {
        "staff_member_id": staff.id,
        "role": staff.role,
        "has_login": login_uid is not None,
        "permissions": _effective_permission_map(staff.role, overrides),
    }


@router.post("/staff-permissions/{staff_member_id}")
async def set_staff_permission(
    staff_member_id: int,
    data: StaffPermissionSetRequest,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Grant/deny a managed key for a staff member (or reset to the role default).

    The override row is keyed on the staff member's *login* user id, so it takes
    effect in ``has_permission`` over the role default (ISSUE-034). Owner-scoped:
    editing another tenant's staff member is rejected (404 from the lookup).
    """
    from dependencies.permissions import MANAGED_PERMISSION_KEYS, role_allows
    from models.permissions import Permissions

    if data.permission_key not in MANAGED_PERMISSION_KEYS:
        raise HTTPException(
            status_code=400, detail=f"Unknown or unmanaged permission key: {data.permission_key}"
        )

    staff, login_uid = await _resolve_owned_staff_login(
        db, scope.owner_user_id, staff_member_id
    )
    if login_uid is None:
        raise HTTPException(
            status_code=400,
            detail="Staff member has no login account to scope permissions to",
        )

    existing = (
        await db.execute(
            select(Permissions).where(
                Permissions.user_id == login_uid,
                Permissions.permission_key == data.permission_key,
            )
        )
    ).scalar_one_or_none()

    if data.is_granted is None:
        # Reset: drop the override so the key falls back to the role default.
        if existing is not None:
            await db.delete(existing)
        await db.commit()
        effective = role_allows(staff.role, data.permission_key)
        return {
            "staff_member_id": staff.id,
            "permission_key": data.permission_key,
            "override": None,
            "effective": effective,
        }

    if existing is not None:
        existing.is_granted = data.is_granted
        existing.granted_by = str(current_user.id)
    else:
        db.add(
            Permissions(
                user_id=login_uid,
                permission_key=data.permission_key,
                is_granted=data.is_granted,
                granted_by=str(current_user.id),
            )
        )
    await db.commit()
    return {
        "staff_member_id": staff.id,
        "permission_key": data.permission_key,
        "override": data.is_granted,
        "effective": data.is_granted,
    }


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
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Generate Arabic-only PDF invoice HTML from a transaction ID."""
    from models.clients import Clients
    from models.transactions import Transactions

    # Fetch transaction
    result = await db.execute(
        select(Transactions).where(
            Transactions.id == data.transaction_id,
            Transactions.user_id == owner_id,
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
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Generate ZATCA Phase 2 compliant XML invoice."""
    from models.clients import Clients
    from models.transactions import Transactions

    result = await db.execute(
        select(Transactions).where(
            Transactions.id == data.transaction_id,
            Transactions.user_id == owner_id,
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
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Get low stock alerts for current user's products."""
    alerts = await LowStockChecker.check_low_stock(
        db=db, user_id=owner_id, threshold=threshold
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
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Test a webhook by sending a test event."""
    from models.webhooks import Webhooks

    result = await db.execute(
        select(Webhooks).where(
            Webhooks.id == data.webhook_id,
            Webhooks.user_id == owner_id,
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

    # Persist the test delivery so it surfaces in the Delivery Logs tab (ISSUE-029).
    from services.production import record_delivery

    await record_delivery(
        db, owner_id, webhook.id, webhook.url, "test.ping", dispatch_result
    )

    return dispatch_result


@router.get("/webhooks/logs")
async def list_webhook_deliveries(
    limit: int = Query(default=50, ge=1, le=500),
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Return the merchant's webhook delivery history, newest first (ISSUE-029).

    Each row is joined to its webhook name and carries ``success``/``status_code``
    so the WebhookManagement "Delivery Logs" tab and its "Deliveries Today" stat
    render real outcomes instead of a swallowed 404.
    """
    from models.webhook_deliveries import Webhook_deliveries
    from models.webhooks import Webhooks

    result = await db.execute(
        select(Webhook_deliveries, Webhooks.name)
        .outerjoin(Webhooks, Webhooks.id == Webhook_deliveries.webhook_id)
        .where(Webhook_deliveries.user_id == owner_id)
        .order_by(Webhook_deliveries.id.desc())
        .limit(limit)
    )
    rows = result.all()
    items = [
        {
            "id": d.id,
            "webhook_id": d.webhook_id,
            "webhook_name": name,
            "event": d.event,
            "url": d.target_url,
            "status": d.status,
            "success": d.status == "delivered",
            "status_code": d.status_code,
            "response_time_ms": d.response_time_ms,
            "attempts": d.attempts,
            "error": d.error,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d, name in rows
    ]
    return {"items": items, "total": len(items)}


# =============================================================================
# Shift Management Endpoints
# =============================================================================
@router.post("/shifts/open")
async def open_shift(
    data: ShiftOpenRequest,
    background_tasks: BackgroundTasks,
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Open a new shift."""
    from models.shifts import Shifts

    # Check for existing open shift
    existing = await db.execute(
        select(Shifts).where(
            Shifts.user_id == owner_id,
            Shifts.status == "open",
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="An open shift already exists. Close it first.")

    now = datetime.now(timezone.utc)
    shift = Shifts(
        user_id=owner_id,
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

    # Domain webhook (ISSUE-051, H25): notify subscribers the shift opened.
    background_tasks.add_task(
        fire_event_background,
        owner_id,
        "shift.opened",
        {
            "shift_id": shift.id,
            "branch_id": shift.branch_id,
            "staff_name": shift.staff_name,
            "opening_cash": shift.opening_cash,
        },
    )

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
    background_tasks: BackgroundTasks,
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Close the current open shift with cash reconciliation."""
    from models.shifts import Shifts

    result = await db.execute(
        select(Shifts).where(
            Shifts.user_id == owner_id,
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

    # Domain webhook (ISSUE-051, H25): notify subscribers the shift closed,
    # carrying the reconciliation outcome integrations care about.
    background_tasks.add_task(
        fire_event_background,
        owner_id,
        "shift.closed",
        {
            "shift_id": shift.id,
            "branch_id": shift.branch_id,
            "closing_cash": data.closing_cash,
            "expected_cash": expected_cash,
            "cash_difference": cash_difference,
        },
    )

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
        "pay_in": recon["pay_in"],
        "pay_out": recon["pay_out"],
        "cash_drops": recon["cash_drops"],
        "total_sales": shift.total_sales,
        "total_transactions": shift.total_transactions,
        "reconciliation": "balanced" if abs(cash_difference) < 0.01 else ("over" if cash_difference > 0 else "short"),
    }


@router.get("/shifts/current")
async def get_current_shift(
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Get the current open shift."""
    from models.shifts import Shifts

    result = await db.execute(
        select(Shifts).where(
            Shifts.user_id == owner_id,
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
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """List the caller's closed shifts (most recent first) for reconciliation."""
    from models.shifts import Shifts

    result = await db.execute(
        select(Shifts)
        .where(Shifts.user_id == owner_id, Shifts.status == "closed")
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


# Cash drawer movements (FIN-04 / POS-09): pay-in / pay-out / cash-drop entries
# recorded against the open shift so the close-time reconciliation accounts for
# cash that entered or left the till outside a sale, and the Z/X-report shows the
# payouts line (RPT-06).
_MOVEMENT_TYPES = {"pay_in", "pay_out", "cash_drop"}


@router.post("/shifts/movements")
async def record_cash_movement(
    data: CashMovementRequest,
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Record a pay-in / pay-out / cash-drop against the caller's open shift.

    There must be an open shift (a drawer movement only makes sense while the till
    is open); ``movement_type`` must be one of pay_in/pay_out/cash_drop and
    ``amount`` a positive magnitude. The movement is owned by ``user_id`` and tied
    to the open shift (SEC-02), and the response carries the recomputed drawer
    expectation so the UI can refresh without a round-trip."""
    from models.shifts import Shifts

    movement_type = (data.movement_type or "").lower()
    if movement_type not in _MOVEMENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail="movement_type must be one of pay_in, pay_out, cash_drop",
        )
    if data.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")

    result = await db.execute(
        select(Shifts).where(
            Shifts.user_id == owner_id,
            Shifts.status == "open",
        )
    )
    shift = result.scalar_one_or_none()
    if not shift:
        raise HTTPException(status_code=404, detail="No open shift to record a cash movement against")

    movement = Cash_movements(
        user_id=owner_id,
        client_id=shift.client_id,
        shift_id=shift.id,
        movement_type=movement_type,
        amount=round(abs(float(data.amount)), 2),
        reason=data.reason,
    )
    db.add(movement)
    await db.commit()
    await db.refresh(movement)

    recon = await compute_shift_cash_reconciliation(db, shift)
    return {
        "id": movement.id,
        "shift_id": shift.id,
        "movement_type": movement.movement_type,
        "amount": movement.amount,
        "reason": movement.reason,
        "expected_cash": recon["expected_cash"],
        "pay_in": recon["pay_in"],
        "pay_out": recon["pay_out"],
        "cash_drops": recon["cash_drops"],
    }


@router.get("/shifts/movements")
async def list_cash_movements(
    shift_id: Optional[int] = Query(None, description="Shift to list movements for; omit for the current open shift"),
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """List the caller's drawer movements for a shift (owner-scoped, SEC-02).

    With ``shift_id`` omitted, lists the caller's open shift's movements; an
    unknown/foreign shift id resolves to no movements (the query is filtered on
    ``user_id``)."""
    from models.shifts import Shifts

    if shift_id is None:
        result = await db.execute(
            select(Shifts).where(
                Shifts.user_id == owner_id,
                Shifts.status == "open",
            )
        )
        shift = result.scalar_one_or_none()
        if not shift:
            return {"movements": [], "total": 0, "pay_in": 0.0, "pay_out": 0.0, "cash_drops": 0.0}
        shift_id = shift.id

    result = await db.execute(
        select(Cash_movements)
        .where(
            Cash_movements.user_id == owner_id,
            Cash_movements.shift_id == shift_id,
        )
        .order_by(Cash_movements.id.desc())
    )
    movements = result.scalars().all()
    pay_in = round(sum(abs(float(m.amount or 0)) for m in movements if (m.movement_type or "") == "pay_in"), 2)
    pay_out = round(sum(abs(float(m.amount or 0)) for m in movements if (m.movement_type or "") == "pay_out"), 2)
    cash_drops = round(sum(abs(float(m.amount or 0)) for m in movements if (m.movement_type or "") == "cash_drop"), 2)
    return {
        "movements": [
            {
                "id": m.id,
                "shift_id": m.shift_id,
                "movement_type": m.movement_type,
                "amount": m.amount,
                "reason": m.reason,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in movements
        ],
        "total": len(movements),
        "pay_in": pay_in,
        "pay_out": pay_out,
        "cash_drops": cash_drops,
    }


# =============================================================================
# Loyalty Points Endpoints
# =============================================================================
@router.post("/loyalty/earn", dependencies=[Depends(require_feature("loyalty"))])
async def earn_loyalty_points(
    data: LoyaltyEarnRequest,
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Earn loyalty points from a transaction."""
    from models.loyalty_points import Loyalty_points
    from models.loyalty_transactions import Loyalty_transactions

    points_earned = int(data.transaction_amount * data.points_rate)

    # Find or create loyalty record
    result = await db.execute(
        select(Loyalty_points).where(
            Loyalty_points.user_id == owner_id,
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
            user_id=owner_id,
            customer_id=data.customer_id,
            points_balance=points_earned,
            total_earned=points_earned,
            total_redeemed=0,
        )
        db.add(new_loyalty)

    # Record the earn leg on the ledger (ISSUE-044) so the balance is auditable
    # and the points carry a dated origin the expiry window measures against.
    if points_earned > 0:
        db.add(
            Loyalty_transactions(
                user_id=owner_id,
                customer_id=data.customer_id,
                type="earned",
                points=points_earned,
                description="Earned on sale",
            )
        )

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
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Redeem loyalty points for a customer."""
    from models.loyalty_points import Loyalty_points
    from models.loyalty_transactions import Loyalty_transactions

    result = await db.execute(
        select(Loyalty_points).where(
            Loyalty_points.user_id == owner_id,
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

    # FIN-05: value the redeemed points from the merchant's server-side program
    # rate, never a client-supplied figure. Fall back to the platform default
    # when no active program is configured.
    from core.money import quantize_money, to_decimal
    from services.loyalty import get_active_program

    program = await get_active_program(db, owner_id)
    rate = (program.redemption_rate if program else None) or DEFAULT_REDEMPTION_RATE
    discount_value = quantize_money(to_decimal(data.points_to_redeem) * to_decimal(rate))

    # Cap the discount at the order subtotal when one is supplied, mirroring the
    # atomic POS path: a redemption can never discount more than the order is
    # worth. Reject (before any balance mutation) rather than silently clamp.
    # FIN-03: an exact Decimal cap — no float +0.01 slop letting a penny through.
    if data.order_subtotal is not None and discount_value > quantize_money(data.order_subtotal):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Redemption value {discount_value:.2f} exceeds order subtotal "
                f"{quantize_money(data.order_subtotal):.2f}"
            ),
        )

    new_balance = (loyalty.points_balance or 0) - data.points_to_redeem
    new_total_redeemed = (loyalty.total_redeemed or 0) + data.points_to_redeem

    await db.execute(
        update(Loyalty_points)
        .where(Loyalty_points.id == loyalty.id)
        .values(points_balance=new_balance, total_redeemed=new_total_redeemed)
    )

    # Record the redeem leg on the ledger (ISSUE-044).
    db.add(
        Loyalty_transactions(
            user_id=owner_id,
            customer_id=data.customer_id,
            type="redeemed",
            points=data.points_to_redeem,
            description="Redeemed for discount",
        )
    )
    await db.commit()

    return {
        "customer_id": data.customer_id,
        "points_redeemed": data.points_to_redeem,
        "discount_value": quantize_money(discount_value),
        "remaining_balance": new_balance,
    }


@router.get("/loyalty/balance")
async def get_loyalty_balance(
    customer_id: int = Query(..., description="Customer ID"),
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Get customer loyalty points balance."""
    from models.loyalty_points import Loyalty_points

    result = await db.execute(
        select(Loyalty_points).where(
            Loyalty_points.user_id == owner_id,
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
# Loyalty Admin Endpoints (ISSUE-028 / C4) — back the LoyaltyProgram page
# =============================================================================
def _config_payload(program) -> dict:
    """Map a ``Loyalty_programs`` row to the admin page's config shape."""
    return {
        "id": program.id,
        "points_per_sar": program.points_per_sar or 0,
        "redemption_rate": program.redemption_rate or 0,
        "min_points_redeem": program.min_redemption_points or 0,
        "points_expiry_days": program.points_expiry_days or 0,
        "is_active": bool(program.is_active),
    }


async def _resolve_config_program(db: AsyncSession, owner_id: str):
    """The authoritative loyalty program for the merchant's config screen (FIN-11).

    Prefer the single active program — the exact one the POS uses via
    ``get_active_program`` — so the config page and the POS never diverge; fall
    back to the most recent program when none is active, so an all-inactive
    config still round-trips.
    """
    from models.loyalty_programs import Loyalty_programs
    from services.loyalty import get_active_program

    active = await get_active_program(db, owner_id)
    if active is not None:
        return active
    result = await db.execute(
        select(Loyalty_programs)
        .where(Loyalty_programs.user_id == owner_id)
        .order_by(Loyalty_programs.id.desc())
    )
    return result.scalars().first()


@router.get("/loyalty/config", dependencies=[Depends(require_feature("loyalty"))])
async def get_loyalty_config(
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Return the merchant's loyalty-program config (the active one), or nulls if none."""
    program = await _resolve_config_program(db, owner_id)
    if not program:
        # No program yet — the page keeps its defaults (it checks points_per_sar != null).
        return {
            "id": None,
            "points_per_sar": None,
            "redemption_rate": None,
            "min_points_redeem": None,
            "points_expiry_days": None,
            "is_active": False,
        }
    return _config_payload(program)


@router.post("/loyalty/config", dependencies=[Depends(require_feature("loyalty"))])
async def save_loyalty_config(
    data: LoyaltyConfigRequest,
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Upsert the merchant's loyalty-program config (single active program, FIN-11)."""
    from models.loyalty_programs import Loyalty_programs
    from routers.pos import get_client_for_user
    from services.loyalty import enforce_single_active_program

    program = await _resolve_config_program(db, owner_id)

    if program:
        await db.execute(
            update(Loyalty_programs)
            .where(Loyalty_programs.id == program.id)
            .values(
                points_per_sar=data.points_per_sar,
                redemption_rate=data.redemption_rate,
                min_redemption_points=data.min_points_redeem,
                points_expiry_days=data.points_expiry_days,
                is_active=data.is_active,
            )
        )
    else:
        client = await get_client_for_user(db, owner_id)
        program = Loyalty_programs(
            user_id=owner_id,
            client_id=client.id,
            name="Rewards",
            points_per_sar=data.points_per_sar,
            redemption_rate=data.redemption_rate,
            min_redemption_points=data.min_points_redeem,
            points_expiry_days=data.points_expiry_days,
            is_active=data.is_active,
        )
        db.add(program)
        await db.flush()

    # Single authoritative active program per tenant: when this config is active,
    # demote any other program that is still active for the merchant.
    if data.is_active:
        await enforce_single_active_program(db, owner_id, program.id)

    await db.commit()
    await db.refresh(program)

    return _config_payload(program)


@router.get("/loyalty/balances", dependencies=[Depends(require_feature("loyalty"))])
async def list_loyalty_balances(
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """List the merchant's customer point balances, joined to the customer name.

    ``available_points`` is the usable balance derived from the ledger after
    aging out credits older than the program's expiry window (ISSUE-044); the
    stored ``points_balance`` remains the lifetime earned-minus-redeemed figure.
    """
    from models.customers import Customers
    from models.loyalty_points import Loyalty_points
    from models.loyalty_programs import Loyalty_programs
    from models.loyalty_transactions import Loyalty_transactions
    from services.loyalty_points import compute_usable_balance

    # The merchant's expiry policy (0/None = points never expire).
    prog_res = await db.execute(
        select(Loyalty_programs.points_expiry_days)
        .where(Loyalty_programs.user_id == owner_id)
        .order_by(Loyalty_programs.id.desc())
    )
    expiry_days = prog_res.scalars().first() or 0

    # All of this merchant's ledger movements, bucketed by customer, for the
    # expiry-aware balance computation.
    tx_res = await db.execute(
        select(Loyalty_transactions).where(Loyalty_transactions.user_id == owner_id)
    )
    ledger: dict = {}
    for tx in tx_res.scalars().all():
        ledger.setdefault(tx.customer_id, []).append(
            {"type": tx.type, "points": tx.points, "created_at": tx.created_at}
        )

    result = await db.execute(
        select(Loyalty_points, Customers.name)
        .outerjoin(Customers, Customers.id == Loyalty_points.customer_id)
        .where(Loyalty_points.user_id == owner_id)
        .order_by(Loyalty_points.updated_at.desc())
    )
    rows = result.all()
    items = [
        {
            "id": lp.id,
            "customer_id": lp.customer_id,
            "customer_name": name or f"Customer #{lp.customer_id}",
            "points_balance": lp.points_balance or 0,
            "available_points": compute_usable_balance(
                ledger.get(lp.customer_id, []), expiry_days=expiry_days
            ),
            "total_earned": lp.total_earned or 0,
            "total_redeemed": lp.total_redeemed or 0,
            "last_activity": lp.updated_at.isoformat() if lp.updated_at else None,
        }
        for lp, name in rows
    ]
    return {"items": items, "total": len(items)}


@router.get("/loyalty/transactions", dependencies=[Depends(require_feature("loyalty"))])
async def list_loyalty_transactions(
    limit: int = Query(default=50, ge=1, le=500),
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Return the merchant's loyalty-point ledger, newest first."""
    from models.customers import Customers
    from models.loyalty_transactions import Loyalty_transactions

    result = await db.execute(
        select(Loyalty_transactions, Customers.name)
        .outerjoin(Customers, Customers.id == Loyalty_transactions.customer_id)
        .where(Loyalty_transactions.user_id == owner_id)
        .order_by(Loyalty_transactions.id.desc())
        .limit(limit)
    )
    rows = result.all()
    items = [
        {
            "id": tx.id,
            "customer_id": tx.customer_id,
            "customer_name": name or f"Customer #{tx.customer_id}",
            "type": tx.type,
            "points": tx.points,
            "description": tx.description,
            "created_at": tx.created_at.isoformat() if tx.created_at else None,
        }
        for tx, name in rows
    ]
    return {"items": items, "total": len(items)}


@router.post("/loyalty/adjust", dependencies=[Depends(require_feature("loyalty"))])
async def adjust_loyalty_points(
    data: LoyaltyAdjustRequest,
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Manually credit ('add') or debit ('deduct') a customer's points + log it.

    Writes a ``loyalty_transactions`` ledger entry alongside the balance change so
    the adjustment is auditable in the Points History tab.
    """
    from models.loyalty_points import Loyalty_points
    from models.loyalty_transactions import Loyalty_transactions
    from routers.pos import get_client_for_user

    if data.type not in ("add", "deduct"):
        raise HTTPException(status_code=400, detail="type must be 'add' or 'deduct'")
    if data.points <= 0:
        raise HTTPException(status_code=400, detail="points must be positive")

    client = await get_client_for_user(db, owner_id)

    result = await db.execute(
        select(Loyalty_points).where(
            Loyalty_points.user_id == owner_id,
            Loyalty_points.customer_id == data.customer_id,
        )
    )
    row = result.scalar_one_or_none()
    current = (row.points_balance or 0) if row else 0
    delta = data.points if data.type == "add" else -data.points

    if current + delta < 0:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient points. Available: {current}, requested deduct: {data.points}",
        )

    new_balance = current + delta
    if row:
        await db.execute(
            update(Loyalty_points)
            .where(Loyalty_points.id == row.id)
            .values(
                points_balance=new_balance,
                total_earned=(row.total_earned or 0) + (data.points if data.type == "add" else 0),
                total_redeemed=(row.total_redeemed or 0) + (data.points if data.type == "deduct" else 0),
            )
        )
    else:
        db.add(
            Loyalty_points(
                user_id=owner_id,
                client_id=client.id,
                customer_id=data.customer_id,
                points_balance=new_balance,
                total_earned=data.points if data.type == "add" else 0,
                total_redeemed=data.points if data.type == "deduct" else 0,
            )
        )

    db.add(
        Loyalty_transactions(
            user_id=owner_id,
            client_id=client.id,
            customer_id=data.customer_id,
            type=data.type,
            points=data.points,
            description=data.reason,
        )
    )
    await db.commit()

    return {
        "customer_id": data.customer_id,
        "type": data.type,
        "points": data.points,
        "points_balance": new_balance,
    }


# =============================================================================
# Bulk Import/Export Endpoints
# =============================================================================
@router.post("/bulk/import")
async def bulk_import(
    data: BulkImportRequest,
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
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
                    user_id=owner_id,
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
                    user_id=owner_id,
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
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Export data as CSV."""
    user_id = owner_id

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
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Global search across products, customers, and transactions."""
    results = await SearchService.global_search(
        db=db, user_id=owner_id, query=q, limit=limit
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
    owner_id: str = Depends(get_owner_id),
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

    client = await get_client_for_user(db, owner_id)
    result = await OfflineSyncService.process_offline_queue(
        db=db,
        user_id=owner_id,
        client_id=client.id,
        queued_transactions=data.transactions,
    )
    return result


# =============================================================================
# Multi-Branch Inventory
# =============================================================================
@router.get("/branches/inventory")
async def get_branch_inventory(
    branch_id: Optional[int] = Query(default=None, description="Filter by branch ID"),
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
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
    branch_query = select(Branches).where(Branches.user_id == owner_id)
    if branch_id:
        branch_query = branch_query.where(Branches.id == branch_id)

    branch_result = await db.execute(branch_query)
    branches = branch_result.scalars().all()

    # Get all products for user
    prod_result = await db.execute(
        select(Products).where(
            Products.user_id == owner_id,
            Products.is_active == True,  # noqa: E712
        )
    )
    products = prod_result.scalars().all()

    # Per-branch ledger overrides, keyed by (branch_id, product_id).
    ledger_result = await db.execute(
        select(Product_branch_stock).where(
            Product_branch_stock.user_id == owner_id
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
            # INV-09 (F-070): inventory is valued at COST (money tied up in stock),
            # never sale price — a stock-on-hand valuation, not a retail markup.
            "total_stock_value": sum((p.cost_price or 0) * _qty(p) for p in products),
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


# INV-06 (F-036): the reasons a stock count/adjustment may carry. ``count`` is a
# physical recount that sets on-hand to the counted figure; ``wastage``/``damage``
# record shrink; ``correction`` fixes a data error; ``restock`` a manual add-back;
# ``other`` is the catch-all. Any other value is rejected (400).
STOCK_ADJUSTMENT_REASONS = frozenset(
    {"count", "wastage", "damage", "correction", "restock", "other"}
)


class StockAdjustmentRequest(BaseModel):
    # Either a product_id (preferred) or a product_name (resolved within the client).
    product_id: Optional[int] = None
    product_name: Optional[str] = None
    # Null ⇒ a client-level adjustment; otherwise the per-branch ledger is adjusted.
    branch_id: Optional[int] = None
    reason: str = "count"
    # The new physical on-hand the count sets the pool to (must be ≥ 0).
    counted_quantity: int
    note: Optional[str] = None


@router.post("/branches/transfer")
async def transfer_branch_stock(
    data: StockTransferRequest,
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
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
    from services.branch_stock import transfer_branch_inventory

    logger.debug("[TRANSFER] user=%s from=%s to=%s qty=%s", current_user.id, data.from_branch_id, data.to_branch_id, data.quantity)

    # POS features are client-scoped — resolve the caller's client row.
    client = (
        await db.execute(select(Clients).where(Clients.user_id == owner_id))
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
                Branches.user_id == owner_id,
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

    # Move stock on the per-branch ledger (source−, dest+) with one conditional
    # decrement + one atomic increment (DAT-04), so concurrent transfers cannot
    # double-move or lose stock. The helper does not commit — we commit once below
    # so the two legs + the audit row land atomically (roll back wholly on any raise).
    src_qty, dst_qty = await transfer_branch_inventory(
        db, owner_id, client.id, int(data.from_branch_id), int(data.to_branch_id), product, qty
    )

    record = StockTransfers(
        user_id=owner_id,
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
        "from_branch_quantity": src_qty,
        "to_branch_quantity": dst_qty,
    }


class StockReceiveRequest(BaseModel):
    # The quantity actually booked in at the destination. Defaults to the full
    # dispatched quantity; a smaller figure records an in-transit discrepancy.
    received_quantity: Optional[int] = None


@router.post("/branches/transfer/dispatch")
async def dispatch_branch_stock(
    data: StockTransferRequest,
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Phase 1 of a two-phase transfer: ship stock out of the source (INV-05, #61).

    Decrements the source branch ledger by N and writes an ``in_transit``
    ``stock_transfers`` row. The destination is **not** credited yet — it lands only
    when the shipment is received (:func:`receive_branch_stock`). Owner-scoped
    (SEC-02); insufficient source stock → 400.
    """
    from models.branches import Branches
    from models.clients import Clients
    from models.products import Products
    from models.stock_transfers import Stock_transfers as StockTransfers
    from services.branch_stock import dispatch_branch_inventory

    client = (
        await db.execute(select(Clients).where(Clients.user_id == owner_id))
    ).scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=403, detail="Only clients can transfer stock")

    qty = int(data.quantity or 0)
    if qty <= 0:
        raise HTTPException(status_code=400, detail="Transfer quantity must be positive")
    if int(data.from_branch_id) == int(data.to_branch_id):
        raise HTTPException(status_code=400, detail="Source and destination branches must differ")

    branch_rows = (
        await db.execute(
            select(Branches).where(
                Branches.user_id == owner_id,
                Branches.id.in_([int(data.from_branch_id), int(data.to_branch_id)]),
            )
        )
    ).scalars().all()
    found_ids = {b.id for b in branch_rows}
    if int(data.from_branch_id) not in found_ids or int(data.to_branch_id) not in found_ids:
        raise HTTPException(status_code=404, detail="Branch not found")

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

    # Ship: atomically decrement the source only (DAT-04). The destination is
    # credited on receive. Conditional decrement → no read-check-write oversell race.
    src_qty = await dispatch_branch_inventory(
        db, owner_id, client.id, int(data.from_branch_id), product, qty
    )

    record = StockTransfers(
        user_id=owner_id,
        client_id=client.id,
        from_branch_id=int(data.from_branch_id),
        to_branch_id=int(data.to_branch_id),
        product_id=product.id,
        product_name=product.name,
        quantity=qty,
        status="in_transit",
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
        "from_branch_quantity": src_qty,
    }


@router.post("/branches/transfer/{transfer_id}/receive")
async def receive_branch_stock(
    transfer_id: int,
    data: StockReceiveRequest,
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Phase 2 of a two-phase transfer: book an in-transit shipment in (INV-05, #61).

    Credits the destination branch with the received quantity (default: the full
    dispatched quantity) and closes the transfer (``received``). When fewer units
    arrive than were dispatched, the shortfall is recorded on the transfer as
    ``discrepancy`` — the destination is credited only what actually arrived; the
    source already shed the full dispatched quantity. Owner-scoped (SEC-02); a
    transfer that is not ``in_transit`` → 400.
    """
    from models.clients import Clients
    from models.products import Products
    from models.stock_transfers import Stock_transfers as StockTransfers
    from services.branch_stock import get_or_init_row

    client = (
        await db.execute(select(Clients).where(Clients.user_id == owner_id))
    ).scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=403, detail="Only clients can transfer stock")

    # Owner-scoped fetch — a client can only receive its own transfers (SEC-02).
    record = (
        await db.execute(
            select(StockTransfers).where(
                StockTransfers.id == int(transfer_id),
                StockTransfers.user_id == owner_id,
            )
        )
    ).scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Transfer not found")
    if record.status != "in_transit":
        raise HTTPException(
            status_code=400,
            detail=f"Transfer is not in transit (status: {record.status})",
        )

    dispatched = int(record.quantity or 0)
    received = data.received_quantity if data.received_quantity is not None else dispatched
    received = int(received)
    if received < 0:
        raise HTTPException(status_code=400, detail="Received quantity cannot be negative")
    if received > dispatched:
        raise HTTPException(
            status_code=400,
            detail=f"Received quantity ({received}) exceeds dispatched ({dispatched})",
        )

    product = (
        await db.execute(
            select(Products).where(
                Products.id == record.product_id, Products.client_id == client.id
            )
        )
    ).scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    dst = await get_or_init_row(
        db, owner_id, client.id, int(record.to_branch_id), product
    )
    dst.quantity = (dst.quantity or 0) + received

    record.received_quantity = received
    record.discrepancy = dispatched - received
    record.status = "received"
    await db.commit()
    await db.refresh(record)

    return {
        "id": record.id,
        "from_branch_id": record.from_branch_id,
        "to_branch_id": record.to_branch_id,
        "product_id": record.product_id,
        "product_name": record.product_name,
        "quantity": record.quantity,
        "received_quantity": record.received_quantity,
        "discrepancy": record.discrepancy,
        "status": record.status,
        "to_branch_quantity": dst.quantity,
    }


@router.get("/branches/transfers")
async def list_branch_transfers(
    branch_id: Optional[int] = None,
    product_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = 100,
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """List the caller's inter-branch transfer history (ISSUE-060, INV-05).

    The Branch Management "Transfer Stock" dialog wrote ``stock_transfers`` audit
    rows (F-032) but nothing read them back. Owner-scoped to the caller's login
    account (SEC-02), newest first. ``branch_id`` matches either leg (source OR
    destination); ``product_id`` and ``status`` filter further when given.
    """
    from sqlalchemy import or_

    from models.stock_transfers import Stock_transfers as StockTransfers

    query = select(StockTransfers).where(StockTransfers.user_id == owner_id)
    if branch_id is not None:
        query = query.where(
            or_(
                StockTransfers.from_branch_id == int(branch_id),
                StockTransfers.to_branch_id == int(branch_id),
            )
        )
    if product_id is not None:
        query = query.where(StockTransfers.product_id == int(product_id))
    if (status or "").strip():
        query = query.where(StockTransfers.status == status.strip())
    query = query.order_by(StockTransfers.id.desc()).limit(max(1, min(int(limit), 500)))

    rows = (await db.execute(query)).scalars().all()
    return {
        "items": [
            {
                "id": r.id,
                "from_branch_id": r.from_branch_id,
                "to_branch_id": r.to_branch_id,
                "product_id": r.product_id,
                "product_name": r.product_name,
                "quantity": r.quantity,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
        "total": len(rows),
    }


@router.post("/stock-adjustments")
async def create_stock_adjustment(
    data: StockAdjustmentRequest,
    background_tasks: BackgroundTasks,
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Record a stock count / adjustment with a reason → variance (INV-06, F-036).

    Snapshots the current on-hand (``system_quantity``), sets the stock pool to the
    counted figure, and writes one ``stock_adjustments`` row carrying
    ``variance = counted − system`` and the reason — the variance record every POS
    leader keeps. When ``branch_id`` is given the per-branch ledger
    (``product_branch_stock``, the pool the POS deducts from) is adjusted; otherwise
    the client-level ``products.quantity`` is. Atomic: the stock write and the audit
    row land together, so a rejected request leaves stock untouched. Owner-scoped:
    the product and branch must belong to the caller's client (SEC-02).
    """
    from models.branches import Branches
    from models.clients import Clients
    from models.products import Products
    from models.stock_adjustments import Stock_adjustments as StockAdjustments
    from services.branch_stock import get_or_init_row

    logger.debug(
        "[ADJUST] user=%s product=%s branch=%s reason=%s counted=%s",
        current_user.id, data.product_id, data.branch_id, data.reason, data.counted_quantity,
    )

    # POS features are client-scoped — resolve the caller's client row.
    client = (
        await db.execute(select(Clients).where(Clients.user_id == owner_id))
    ).scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=403, detail="Only clients can adjust stock")

    reason = (data.reason or "count").strip().lower()
    if reason not in STOCK_ADJUSTMENT_REASONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown reason '{reason}'. Allowed: {sorted(STOCK_ADJUSTMENT_REASONS)}",
        )

    counted = int(data.counted_quantity)
    if counted < 0:
        raise HTTPException(status_code=400, detail="Counted quantity cannot be negative")

    # Resolve the product within the caller's client scope (by id, else exact name).
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

    # Apply the count to the chosen pool (no commit — we commit once below so the
    # stock write and the variance row land atomically).
    if data.branch_id is not None:
        branch = (
            await db.execute(
                select(Branches).where(
                    Branches.user_id == owner_id,
                    Branches.id == int(data.branch_id),
                )
            )
        ).scalar_one_or_none()
        if not branch:
            raise HTTPException(status_code=404, detail="Branch not found")
        row = await get_or_init_row(
            db, owner_id, client.id, int(data.branch_id), product
        )
        system_quantity = int(row.quantity or 0)
        row.quantity = counted
    else:
        system_quantity = int(product.quantity or 0)
        product.quantity = counted

    variance = counted - system_quantity
    record = StockAdjustments(
        user_id=owner_id,
        client_id=client.id,
        branch_id=int(data.branch_id) if data.branch_id is not None else None,
        product_id=product.id,
        product_name=product.name,
        reason=reason,
        system_quantity=system_quantity,
        counted_quantity=counted,
        variance=variance,
        note=(data.note or "").strip() or None,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    # Domain webhook (ISSUE-051, H25): an adjustment changed on-hand stock — notify
    # subscribers so inventory integrations stay in sync.
    background_tasks.add_task(
        fire_event_background,
        owner_id,
        "inventory.updated",
        {
            "product_id": record.product_id,
            "product_name": record.product_name,
            "branch_id": record.branch_id,
            "reason": record.reason,
            "system_quantity": record.system_quantity,
            "counted_quantity": record.counted_quantity,
            "variance": record.variance,
        },
    )

    return {
        "id": record.id,
        "product_id": record.product_id,
        "product_name": record.product_name,
        "branch_id": record.branch_id,
        "reason": record.reason,
        "system_quantity": record.system_quantity,
        "counted_quantity": record.counted_quantity,
        "variance": record.variance,
        "note": record.note,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


@router.get("/stock-adjustments")
async def list_stock_adjustments(
    branch_id: Optional[int] = None,
    product_id: Optional[int] = None,
    limit: int = 100,
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """List the caller's stock counts/adjustments (the variance history, INV-06).

    Owner-scoped to the caller's login account (SEC-02); optionally filtered by
    branch or product. Newest first.
    """
    from models.stock_adjustments import Stock_adjustments as StockAdjustments

    query = select(StockAdjustments).where(
        StockAdjustments.user_id == owner_id
    )
    if branch_id is not None:
        query = query.where(StockAdjustments.branch_id == int(branch_id))
    if product_id is not None:
        query = query.where(StockAdjustments.product_id == int(product_id))
    query = query.order_by(StockAdjustments.id.desc()).limit(max(1, min(int(limit), 500)))

    rows = (await db.execute(query)).scalars().all()
    return {
        "items": [
            {
                "id": r.id,
                "product_id": r.product_id,
                "product_name": r.product_name,
                "branch_id": r.branch_id,
                "reason": r.reason,
                "system_quantity": r.system_quantity,
                "counted_quantity": r.counted_quantity,
                "variance": r.variance,
                "note": r.note,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
        "total": len(rows),
    }


# =============================================================================
# API Usage Stats
# =============================================================================
@router.get("/api-usage/stats")
async def get_api_usage_stats(
    current_user: UserResponse = Depends(get_current_user),
    owner_id: str = Depends(get_owner_id),
    db: AsyncSession = Depends(get_db),
):
    """Get API usage statistics for rate plans.

    Scoped to the owning merchant (``owner_user_id``), not the raw actor, so a
    merchant's usage aggregates all their staff's requests (finding H4).
    """
    from models.api_usage import Api_usage

    result = await db.execute(
        select(
            Api_usage.endpoint,
            func.count(Api_usage.id).label("request_count"),
            func.avg(Api_usage.response_time_ms).label("avg_response_time"),
        )
        .where(Api_usage.owner_user_id == owner_id)
        .group_by(Api_usage.endpoint)
    )
    stats = result.all()

    total_result = await db.execute(
        select(func.count(Api_usage.id)).where(
            Api_usage.owner_user_id == owner_id
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