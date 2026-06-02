"""Integration endpoints that wire previously-orphaned services into the request flow.

Before this module, `services/production.py` contained working implementations of
bulk CSV import, global search, webhook dispatch and email that were never reachable
over HTTP. This router exposes them. Bulk import additionally persists the validated
rows (the service only validated them).
"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.auth import get_current_user
from models.products import Products
from routers.features import get_user_role
from schemas.auth import UserResponse
from services.production import (
    BulkImportService,
    EmailService,
    SearchService,
    WebhookDispatcher,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])


# ---------------------------------------------------------------------------
# Bulk CSV import (products)
# ---------------------------------------------------------------------------
class BulkImportRequest(BaseModel):
    csv_content: str


class BulkImportResponse(BaseModel):
    imported: int
    error_count: int
    errors: List[Dict[str, Any]]


async def _require_client(db: AsyncSession, user_id: str) -> int:
    role_info = await get_user_role(db, user_id)
    if role_info["role"] != "client":
        raise HTTPException(status_code=403, detail="Only clients can import products")
    return role_info["entity_id"]


@router.post("/bulk-import/products", response_model=BulkImportResponse)
async def bulk_import_products(
    data: BulkImportRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Validate a products CSV and insert the valid rows for the current client.

    Columns: name (required), price (required), name_ar, barcode, cost_price,
    quantity, category, vat_rate.
    """
    client_id = await _require_client(db, str(current_user.id))

    rows = BulkImportService.parse_csv(data.csv_content)
    validation = BulkImportService.validate_product_rows(rows)

    imported = 0
    for row in validation["valid_rows"]:
        product = Products(
            user_id=str(current_user.id),
            client_id=client_id,
            name=row["name"],
            name_ar=row.get("name_ar") or None,
            barcode=row.get("barcode") or None,
            price=float(row["price"]),
            cost_price=float(row["cost_price"]) if row.get("cost_price") else None,
            quantity=int(row["quantity"]) if row.get("quantity") else 0,
            category=row.get("category") or None,
            vat_rate=float(row["vat_rate"]) if row.get("vat_rate") else 15.0,
            is_active=True,
        )
        db.add(product)
        imported += 1

    await db.commit()
    return BulkImportResponse(
        imported=imported,
        error_count=validation["error_count"],
        errors=validation["errors"],
    )


# ---------------------------------------------------------------------------
# Global search
# ---------------------------------------------------------------------------
class GlobalSearchResponse(BaseModel):
    products: List[Dict[str, Any]]
    customers: List[Dict[str, Any]]
    transactions: List[Dict[str, Any]]


@router.get("/search", response_model=GlobalSearchResponse)
async def global_search(
    q: str = Query(..., min_length=1, description="Search term"),
    limit: int = Query(20, ge=1, le=100),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Search products, customers and transactions owned by the current user."""
    results = await SearchService.global_search(db, str(current_user.id), q, limit=limit)
    return GlobalSearchResponse(**results)


# ---------------------------------------------------------------------------
# Webhook test dispatch
# ---------------------------------------------------------------------------
class WebhookDispatchRequest(BaseModel):
    url: str
    event: str
    payload: Dict[str, Any] = {}
    secret: str = "changeme"


@router.post("/webhooks/dispatch")
async def dispatch_webhook(
    data: WebhookDispatchRequest,
    current_user: UserResponse = Depends(get_current_user),
):
    """Dispatch a signed webhook event (HMAC-SHA256). Stub delivery in dev."""
    return await WebhookDispatcher.dispatch(
        url=data.url, event=data.event, payload=data.payload, secret=data.secret
    )


# ---------------------------------------------------------------------------
# Email send
# ---------------------------------------------------------------------------
class EmailSendRequest(BaseModel):
    to_email: str
    subject: str
    body: str
    html_body: Optional[str] = None


@router.post("/email/send")
async def send_email(
    data: EmailSendRequest,
    current_user: UserResponse = Depends(get_current_user),
):
    """Send an email via the EmailService (stub mode logs; configure SMTP for prod)."""
    return await EmailService.send_email(
        to_email=data.to_email,
        subject=data.subject,
        body=data.body,
        html_body=data.html_body,
    )
