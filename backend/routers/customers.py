import json
import logging
from typing import List, Optional

from datetime import datetime, date, timezone

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services.customers import CustomersService
from services.production import fire_event_background
from services.store_credit import StoreCreditError, StoreCreditService
from services.birthday_rewards import BirthdayRewardsService
from services.customer_groups import CustomerGroupsService
from services.campaigns import CampaignsService
from services.customer_notes import CustomerNoteError, CustomerNotesService
from dependencies.auth import get_admin_user, get_current_user
from dependencies.tenancy import TenantScope, get_tenant_scope
from models.audit_logs import Audit_logs
from models.transactions import Transactions
# Eager import so the store-credit ledger table registers on Base.metadata at
# startup (mirrors the gift-card ledger / branch-table pattern), #221.
from models.store_credit_ledger import StoreCreditLedger  # noqa: F401
# Eager import so the customer_groups table registers on Base.metadata too (#221).
from models.customer_groups import CustomerGroup  # noqa: F401
# Eager import so the campaigns table registers on Base.metadata too (#221).
from models.campaigns import Campaign  # noqa: F401
# Eager import so the customer_notes table registers on Base.metadata too (#221).
from models.customer_notes import CustomerNote  # noqa: F401
from schemas.auth import UserResponse

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/entities/customers", tags=["customers"])


# ---------- Pydantic Schemas ----------
class CustomersData(BaseModel):
    """Entity data schema (for create/update)"""
    name: str
    phone: str = None
    email: str = None
    vat_number: str = None  # buyer VAT for B2B invoices (CRM-01)
    notes: str = None
    total_purchases: float = None
    visit_count: int = None
    marketing_consent: Optional[bool] = None  # PDPL opt-in (SEC-05 / CRM-05)
    tags: Optional[List[str]] = None  # segmentation labels (CRM-04 / F-039)
    date_of_birth: Optional[date] = None  # CRM birthday rewards (#221)


class CustomersUpdateData(BaseModel):
    """Update entity data (partial updates allowed)"""
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    vat_number: Optional[str] = None  # buyer VAT for B2B invoices (CRM-01)
    notes: Optional[str] = None
    total_purchases: Optional[float] = None
    visit_count: Optional[int] = None
    marketing_consent: Optional[bool] = None  # PDPL opt-in (SEC-05 / CRM-05)
    tags: Optional[List[str]] = None  # segmentation labels (CRM-04 / F-039)
    date_of_birth: Optional[date] = None  # CRM birthday rewards (#221)


class CustomersResponse(BaseModel):
    """Entity response schema"""
    id: int
    user_id: str
    # ARC-05: the owning merchant's client id (null for legacy rows pre-backfill).
    client_id: Optional[int] = None
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    vat_number: Optional[str] = None
    notes: Optional[str] = None
    total_purchases: Optional[float] = None
    visit_count: Optional[int] = None
    marketing_consent: Optional[bool] = None
    consent_updated_at: Optional[datetime] = None
    pii_erased_at: Optional[datetime] = None
    # CRM blacklist (#221): ``blacklisted`` is a derived flag (true iff
    # ``blacklisted_at`` is set) so the client never has to interpret the timestamp.
    blacklisted: Optional[bool] = None
    blacklisted_at: Optional[datetime] = None
    blacklist_reason: Optional[str] = None
    # CRM groups & tiers (#221): the named group this customer belongs to, or null.
    group_id: Optional[int] = None
    # CRM birthday rewards (#221): the customer's date of birth, or null when unknown.
    date_of_birth: Optional[date] = None
    # Segmentation labels (CRM-04 / F-039). Stored as a JSON string on the ORM
    # row; the validator below parses it back into a list for the API so the
    # client always sees ``tags`` as a real array (or null when untagged).
    tags: Optional[List[str]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

    @field_validator("tags", mode="before")
    @classmethod
    def _parse_tags(cls, v):
        # The ORM column is a JSON-encoded string; accept that, an already-parsed
        # list, or null. Anything malformed degrades to null rather than 500ing
        # a customer read.
        if v is None or v == "":
            return None
        if isinstance(v, list):
            return [str(t) for t in v]
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
            except (ValueError, TypeError):
                return None
            return [str(t) for t in parsed] if isinstance(parsed, list) else None
        return None


def _serialize_tags(payload: dict) -> dict:
    """Encode an inbound ``tags`` list to the JSON string the column stores.

    Mutates ``payload`` in place (mirrors the ``consent_updated_at`` stamping the
    handlers already do). Trims blanks/dedupes order-preserving; an empty result
    clears the column (None). A non-list value is left untouched.
    """
    if "tags" in payload and isinstance(payload["tags"], list):
        seen = set()
        cleaned = []
        for tag in payload["tags"]:
            label = str(tag).strip()
            if label and label.lower() not in seen:
                seen.add(label.lower())
                cleaned.append(label)
        payload["tags"] = json.dumps(cleaned, ensure_ascii=False) if cleaned else None
    return payload


class CustomersListResponse(BaseModel):
    """List response schema"""
    items: List[CustomersResponse]
    total: int
    skip: int
    limit: int


class CustomersBatchCreateRequest(BaseModel):
    """Batch create request"""
    items: List[CustomersData]


class CustomersBatchUpdateItem(BaseModel):
    """Batch update item"""
    id: int
    updates: CustomersUpdateData


class CustomersBatchUpdateRequest(BaseModel):
    """Batch update request"""
    items: List[CustomersBatchUpdateItem]


class CustomersBatchDeleteRequest(BaseModel):
    """Batch delete request"""
    ids: List[int]


# ---------- Routes ----------
@router.get("", response_model=CustomersListResponse)
async def query_customerss(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Query customerss with filtering, sorting, and pagination (user can only see their own records)"""
    logger.debug(f"Querying customerss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")
    
    service = CustomersService(db)
    try:
        # Parse query JSON if provided
        query_dict = None
        if query:
            try:
                query_dict = json.loads(query)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid query JSON format")
        
        result = await service.get_list(
            skip=skip, 
            limit=limit,
            query_dict=query_dict,
            sort=sort,
            user_id=scope.owner_user_id,
        )
        logger.debug(f"Found {result['total']} customerss")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying customerss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/all", response_model=CustomersListResponse)
async def query_customerss_all(
    query: str = Query(None, description="Query conditions (JSON string)"),
    sort: str = Query(None, description="Sort field (prefix with '-' for descending)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=2000, description="Max number of records to return"),
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    # Query customerss with filtering, sorting, and pagination without user limitation
    logger.debug(f"Querying customerss: query={query}, sort={sort}, skip={skip}, limit={limit}, fields={fields}")

    service = CustomersService(db)
    try:
        # Parse query JSON if provided
        query_dict = None
        if query:
            try:
                query_dict = json.loads(query)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid query JSON format")

        result = await service.get_list(
            skip=skip,
            limit=limit,
            query_dict=query_dict,
            sort=sort
        )
        logger.debug(f"Found {result['total']} customerss")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying customerss: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


# ---------- M5·CRM (#221) — customer groups & membership tiers ----------
# Declared BEFORE the `/{id}` routes so the literal `/groups` collection path is
# matched ahead of the int path-param (which would otherwise 422 on "groups").
class CustomerGroupData(BaseModel):
    """Body for creating a customer group."""
    name: str
    tier: Optional[str] = None
    discount_percent: Optional[float] = None


class CustomerGroupResponse(BaseModel):
    """A named customer group (segment) with its tier and default discount."""
    id: int
    user_id: str
    client_id: Optional[int] = None
    name: str
    tier: Optional[str] = None
    discount_percent: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CustomerGroupListResponse(BaseModel):
    """List of the owner's customer groups."""
    items: List[CustomerGroupResponse]
    total: int


class CustomerGroupAssignData(BaseModel):
    """Body for assigning a customer to a group."""
    group_id: int


@router.get("/groups", response_model=CustomerGroupListResponse)
async def list_customer_groups(
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """List this merchant's customer groups (CRM, #221). Owner-scoped (SEC-02)."""
    groups = await CustomerGroupsService(db).get_list(user_id=scope.owner_user_id)
    return {
        "items": [CustomerGroupResponse.model_validate(g) for g in groups],
        "total": len(groups),
    }


@router.post("/groups", response_model=CustomerGroupResponse, status_code=201)
async def create_customer_group(
    data: CustomerGroupData,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Create a named customer group with a tier + optional discount (CRM, #221)."""
    if not (data.name or "").strip():
        raise HTTPException(status_code=400, detail="Group name is required")
    group = await CustomerGroupsService(db).create(
        user_id=scope.owner_user_id or str(current_user.id),
        client_id=scope.client_id,
        name=data.name,
        tier=data.tier,
        discount_percent=data.discount_percent,
    )
    return CustomerGroupResponse.model_validate(group)


# ---------- M5·CRM (#221) — marketing campaigns ----------
# Declared BEFORE the `/{id}` routes so the literal `/campaigns` collection path is
# matched ahead of the int path-param (which would otherwise 422 on "campaigns").
class CampaignData(BaseModel):
    """Body for creating a marketing campaign."""
    name: str
    channel: str = "sms"
    message: Optional[str] = None
    target_group_id: Optional[int] = None


class CampaignResponse(BaseModel):
    """A marketing campaign with its channel, target group and resolved audience."""
    id: int
    user_id: str
    client_id: Optional[int] = None
    name: str
    channel: str
    message: Optional[str] = None
    target_group_id: Optional[int] = None
    status: str
    audience_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CampaignListResponse(BaseModel):
    """List of the owner's campaigns."""
    items: List[CampaignResponse]
    total: int


@router.get("/campaigns", response_model=CampaignListResponse)
async def list_campaigns(
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """List this merchant's marketing campaigns (CRM, #221). Owner-scoped (SEC-02)."""
    service = CampaignsService(db)
    campaigns = await service.get_list(user_id=scope.owner_user_id)
    items = []
    for c in campaigns:
        resp = CampaignResponse.model_validate(c)
        resp.audience_count = await service.audience_count(c, user_id=scope.owner_user_id)
        items.append(resp)
    return {"items": items, "total": len(items)}


@router.post("/campaigns", response_model=CampaignResponse, status_code=201)
async def create_campaign(
    data: CampaignData,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Create a marketing campaign, optionally targeting a group (CRM, #221).

    Owner-scoped (SEC-02): a foreign/unknown ``target_group_id`` → 404."""
    if not (data.name or "").strip():
        raise HTTPException(status_code=400, detail="Campaign name is required")
    service = CampaignsService(db)
    owner = scope.owner_user_id or str(current_user.id)
    campaign = await service.create(
        user_id=owner,
        client_id=scope.client_id,
        name=data.name,
        channel=data.channel,
        message=data.message,
        target_group_id=data.target_group_id,
    )
    if campaign is None:
        raise HTTPException(status_code=404, detail="Target group not found")
    resp = CampaignResponse.model_validate(campaign)
    resp.audience_count = await service.audience_count(campaign, user_id=owner)
    return resp


# ---------- M5·CRM (#221) — birthday rewards ----------
# Declared BEFORE the `/{id}` routes so the literal `/birthday-rewards` collection
# path is matched ahead of the int path-param (which would 422 on the literal).
class BirthdayRewardRunData(BaseModel):
    """Body for running the birthday-reward batch.

    ``amount`` is the store credit (positive magnitude) granted to each matching
    customer. ``on_date`` is the day to reward for (month/day match); it defaults to
    today when omitted so the merchant can simply "run today's birthdays"."""
    amount: float
    on_date: Optional[date] = None


class BirthdayRewardRow(BaseModel):
    """One customer rewarded by a birthday-reward run."""
    customer_id: int
    name: str
    balance: float


class BirthdayRewardRunResponse(BaseModel):
    """The outcome of a birthday-reward run: who was rewarded and with how much."""
    on_date: date
    amount: float
    count: int
    rewarded: List[BirthdayRewardRow]


@router.post("/birthday-rewards", response_model=BirthdayRewardRunResponse)
async def run_birthday_rewards(
    data: BirthdayRewardRunData,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Grant store credit to every own customer whose birthday is ``on_date`` (#221).

    Owner-scoped (SEC-02): only the caller's own customers are touched. Idempotent
    per birthday year (re-running the same day never double-grants); blacklisted and
    erased customers are skipped. A non-positive ``amount`` → 400."""
    on_date = data.on_date or date.today()
    try:
        rewarded = await BirthdayRewardsService(db).run(
            user_id=scope.owner_user_id,
            client_id=scope.client_id,
            on_date=on_date,
            amount=data.amount,
        )
    except StoreCreditError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "on_date": on_date,
        "amount": data.amount,
        "count": len(rewarded),
        "rewarded": rewarded,
    }


@router.get("/{id}", response_model=CustomersResponse)
async def get_customers(
    id: int,
    fields: str = Query(None, description="Comma-separated list of fields to return"),
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Get a single customers by ID (user can only see their own records)"""
    logger.debug(f"Fetching customers with id: {id}, fields={fields}")
    
    service = CustomersService(db)
    try:
        result = await service.get_by_id(id, user_id=scope.owner_user_id)
        if not result:
            logger.warning(f"Customers with id {id} not found")
            raise HTTPException(status_code=404, detail="Customers not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching customers {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


# ---------- PDPL data-subject rights (SEC-05 / F-050) ----------
class DataSubjectTransaction(BaseModel):
    """A fiscal record linked to the data subject (read-only, retained)."""
    id: int
    invoice_number: str
    total_amount: Optional[float] = None
    status: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CustomerDataExportResponse(BaseModel):
    """PDPL right-to-access / portability bundle for one customer."""
    customer: CustomersResponse
    transactions: List[DataSubjectTransaction]
    transaction_count: int
    # Why some PII (buyer name/phone/VAT on invoices) is retained even after an
    # erasure request — ZATCA's 6-year fiscal-retention obligation overrides
    # erasure for fiscal records (a lawful-basis exemption under PDPL).
    retention_notice: str


def _linked_transactions_filter(customer):
    """Match the customer's fiscal rows by the PII denormalized onto a sale.

    Sales copy ``customer_name``/``customer_phone`` at ring-up time (there is no
    customer FK on ``transactions``). Phone is the most reliable identifier; fall
    back to name. After erasure both are cleared so nothing links back.
    """
    conditions = []
    if customer.phone:
        conditions.append(Transactions.customer_phone == customer.phone)
    if customer.name:
        conditions.append(Transactions.customer_name == customer.name)
    return conditions


@router.get("/{id}/data-export", response_model=CustomerDataExportResponse)
async def export_customer_data(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """PDPL (SEC-05) data-subject access/portability: export everything held about
    one customer — their CRM record plus every fiscal transaction linked to them.

    Owner-scoped: the merchant can only export a customer in their own scope
    (a foreign/unknown id → 404, SEC-02).
    """
    logger.debug(f"PDPL data export for customer {id}")
    service = CustomersService(db)
    try:
        customer = await service.get_by_id(id, user_id=scope.owner_user_id)
        if not customer:
            raise HTTPException(status_code=404, detail="Customers not found")

        conditions = _linked_transactions_filter(customer)
        transactions = []
        if conditions:
            result = await db.execute(
                select(Transactions)
                .where(
                    Transactions.user_id == scope.owner_user_id,
                    or_(*conditions),
                )
                .order_by(Transactions.id.desc())
            )
            transactions = result.scalars().all()

        return {
            "customer": customer,
            "transactions": transactions,
            "transaction_count": len(transactions),
            "retention_notice": (
                "Fiscal records (invoices/credit notes) are retained for 6 years "
                "under ZATCA tax law and are not erased by a data-subject request."
            ),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting customer {id} data: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/{id}/erase", response_model=CustomersResponse)
async def erase_customer_pii(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """PDPL (SEC-05) right-to-erasure: tombstone a customer's personal data.

    Nulls the PII fields (phone/email/VAT/notes), tombstones the name, withdraws
    marketing consent and stamps ``pii_erased_at``. The row is retained (not hard
    deleted) so retained fiscal transactions stay referentially intact; those
    fiscal records keep their own buyer block under the ZATCA-retention exemption.
    The action is audited (SEC-07). Owner-scoped (a foreign/unknown id → 404).
    Idempotent — erasing an already-erased customer is a no-op that still 200s.
    """
    logger.debug(f"PDPL erasure for customer {id}")
    service = CustomersService(db)
    try:
        customer = await service.get_by_id(id, user_id=scope.owner_user_id)
        if not customer:
            raise HTTPException(status_code=404, detail="Customers not found")

        # ``name`` is NOT NULL — tombstone it rather than null it.
        customer.name = "[erased]"
        customer.phone = None
        customer.email = None
        customer.vat_number = None
        customer.notes = None
        customer.marketing_consent = False
        now = datetime.now()
        customer.consent_updated_at = now
        customer.pii_erased_at = now

        db.add(
            Audit_logs(
                user_id=str(current_user.id),
                action="PDPL_ERASE_CUSTOMER",
                entity_type="customers",
                entity_id=str(customer.id),
                details=f"Erased PII for customer {customer.id} (PDPL right-to-erasure)",
            )
        )

        await db.commit()
        await db.refresh(customer)
        logger.info(f"Customer {id} PII erased (PDPL)")
        return customer
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error erasing customer {id} PII: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


# ---------- CRM-04 (F-039) — computed RFM-lite / lifetime-value insights ----------
# A sale row contributes to revenue; a credit note (status="credit_note") reverses
# part of it (F-007). A voided/held row is not a settled sale. We exclude both so
# the lifetime value nets refunds and counts only real visits.
_NON_SALE_STATUSES = ("credit_note", "voided", "held")


class CustomerInsightsResponse(BaseModel):
    """RFM-lite + lifetime value for one customer, computed from linked sales."""
    customer_id: int
    gross_sales: float        # sum of settled sale totals (incl. VAT)
    refunds: float            # sum of credit-note totals routed back
    lifetime_value: float     # net = gross_sales - refunds (monetary)
    visit_count: int          # settled sale count (frequency)
    average_basket: float     # gross_sales / visit_count (0 when no visits)
    first_purchase_at: Optional[datetime] = None
    last_purchase_at: Optional[datetime] = None
    recency_days: Optional[int] = None  # days since the last settled sale
    segment: str              # rfm-lite bucket: new / regular / vip / at_risk


def _rfm_segment(visit_count: int, recency_days: Optional[int], lifetime_value: float) -> str:
    """A deterministic RFM-lite bucket (parity with how the KSA leaders label).

    * ``new`` — no settled purchases yet (a record with no sales / just added).
    * ``at_risk`` — has bought before but not in the last 90 days (lapsing).
    * ``vip`` — frequent (>=5 visits) or high spend (>= 5000 SAR) and still active.
    * ``regular`` — everyone else who has bought recently.
    """
    if visit_count <= 0 or recency_days is None:
        return "new"
    if recency_days > 90:
        return "at_risk"
    if visit_count >= 5 or lifetime_value >= 5000:
        return "vip"
    return "regular"


@router.get("/{id}/insights", response_model=CustomerInsightsResponse)
async def get_customer_insights(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """CRM-04 (F-039): computed lifetime value + RFM-lite for one customer.

    Aggregates the customer's linked fiscal rows **in SQL** (one row per query —
    never load-everything, OPS-05): gross settled sales, refunds (credit notes)
    netted out for the lifetime value, visit count, and first/last purchase dates.
    Transactions carry no customer FK, so they are matched by the PII denormalized
    onto the sale (phone, then name) — the same join the PDPL export uses.

    Owner-scoped (SEC-02): a foreign/unknown customer id → 404; an erased customer
    (PII cleared) has no link key and returns zeroes.
    """
    logger.debug(f"Computing CRM insights for customer {id}")
    service = CustomersService(db)
    try:
        customer = await service.get_by_id(id, user_id=scope.owner_user_id)
        if not customer:
            raise HTTPException(status_code=404, detail="Customers not found")

        conditions = _linked_transactions_filter(customer)
        gross_sales = 0.0
        refunds = 0.0
        visit_count = 0
        first_purchase_at = None
        last_purchase_at = None

        if conditions:
            link = and_(
                Transactions.user_id == scope.owner_user_id,
                or_(*conditions),
            )
            status_col = func.coalesce(Transactions.status, "completed")

            # Settled sales — gross revenue, frequency, recency, in one aggregate row.
            sales_row = (
                await db.execute(
                    select(
                        func.coalesce(func.sum(Transactions.total_amount), 0.0),
                        func.count(Transactions.id),
                        func.min(Transactions.created_at),
                        func.max(Transactions.created_at),
                    ).where(link, status_col.notin_(_NON_SALE_STATUSES))
                )
            ).one()
            gross_sales = float(sales_row[0] or 0.0)
            visit_count = int(sales_row[1] or 0)
            first_purchase_at = sales_row[2]
            last_purchase_at = sales_row[3]

            # Refunds — credit-note totals routed back (F-007), netted from LTV.
            refunds = float(
                (
                    await db.execute(
                        select(func.coalesce(func.sum(Transactions.total_amount), 0.0)).where(
                            link, status_col == "credit_note"
                        )
                    )
                ).scalar()
                or 0.0
            )

        lifetime_value = round(gross_sales - refunds, 2)
        average_basket = round(gross_sales / visit_count, 2) if visit_count else 0.0

        recency_days = None
        if last_purchase_at is not None:
            ref = last_purchase_at
            if ref.tzinfo is None:
                ref = ref.replace(tzinfo=timezone.utc)
            recency_days = max((datetime.now(timezone.utc) - ref).days, 0)

        return {
            "customer_id": customer.id,
            "gross_sales": round(gross_sales, 2),
            "refunds": round(refunds, 2),
            "lifetime_value": lifetime_value,
            "visit_count": visit_count,
            "average_basket": average_basket,
            "first_purchase_at": first_purchase_at,
            "last_purchase_at": last_purchase_at,
            "recency_days": recency_days,
            "segment": _rfm_segment(visit_count, recency_days, lifetime_value),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error computing insights for customer {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


# ---------- M5·CRM (#221) — per-customer purchase timeline ----------
class PurchaseTimelineEvent(BaseModel):
    """One money-moving event in a customer's purchase history."""
    id: int
    invoice_number: Optional[str] = None
    total_amount: Optional[float] = None
    status: Optional[str] = None
    # "sale" for a settled purchase, "refund" for a credit note routed back.
    kind: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PurchaseTimelineResponse(BaseModel):
    """A customer's purchase history as a chronological timeline + a summary."""
    customer_id: int
    events: List[PurchaseTimelineEvent]   # newest-first
    purchase_count: int                   # settled sales only (refunds excluded)
    total_spent: float                    # net = gross settled sales - refunds
    first_purchase_at: Optional[datetime] = None
    last_purchase_at: Optional[datetime] = None


@router.get("/{id}/timeline", response_model=PurchaseTimelineResponse)
async def get_customer_timeline(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """CRM (#221): a customer's purchase history as a chronological timeline.

    Each settled sale and each refund (credit note) becomes a timeline event,
    newest-first, alongside a summary — how many purchases, net total spent, and the
    first/last purchase dates. Voided/held rows are not purchases and are excluded.
    Transactions carry no customer FK, so events are matched by the PII denormalized
    onto the sale (phone, then name) — the same join the PDPL export and the RFM
    insights endpoint use.

    Owner-scoped (SEC-02): a foreign/unknown customer id → 404; another tenant's
    sales never bleed in, and an erased customer (PII cleared) has no link key and
    returns an empty timeline.
    """
    logger.debug(f"Building purchase timeline for customer {id}")
    service = CustomersService(db)
    try:
        customer = await service.get_by_id(id, user_id=scope.owner_user_id)
        if not customer:
            raise HTTPException(status_code=404, detail="Customers not found")

        events: List[dict] = []
        conditions = _linked_transactions_filter(customer)
        if conditions:
            status_col = func.coalesce(Transactions.status, "completed")
            rows = (
                await db.execute(
                    select(Transactions)
                    .where(
                        Transactions.user_id == scope.owner_user_id,
                        or_(*conditions),
                        status_col.notin_(("voided", "held")),
                    )
                    .order_by(Transactions.created_at.desc(), Transactions.id.desc())
                )
            ).scalars().all()
            for t in rows:
                kind = "refund" if (t.status or "completed") == "credit_note" else "sale"
                events.append(
                    {
                        "id": t.id,
                        "invoice_number": t.invoice_number,
                        "total_amount": t.total_amount,
                        "status": t.status,
                        "kind": kind,
                        "created_at": t.created_at,
                    }
                )

        sales = [e for e in events if e["kind"] == "sale"]
        gross = sum(e["total_amount"] or 0.0 for e in sales)
        refunds = sum(e["total_amount"] or 0.0 for e in events if e["kind"] == "refund")
        sale_dates = [e["created_at"] for e in sales if e["created_at"] is not None]

        return {
            "customer_id": customer.id,
            "events": events,
            "purchase_count": len(sales),
            "total_spent": round(gross - refunds, 2),
            "first_purchase_at": min(sale_dates) if sale_dates else None,
            "last_purchase_at": max(sale_dates) if sale_dates else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error building timeline for customer {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("", response_model=CustomersResponse, status_code=201)
async def create_customers(
    data: CustomersData,
    background_tasks: BackgroundTasks,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Create a new customers"""
    logger.debug(f"Creating new customers with data: {data}")

    owner_id = scope.owner_user_id or str(current_user.id)
    service = CustomersService(db)
    try:
        create_dict = data.model_dump()
        # PDPL (SEC-05): stamp when consent was first recorded so the merchant can
        # evidence the opt-in.
        if create_dict.get("marketing_consent") is not None:
            create_dict["consent_updated_at"] = datetime.now()
        # CRM-04 (F-039): encode the tags list to the JSON string the column holds.
        _serialize_tags(create_dict)
        result = await service.create(create_dict, user_id=owner_id, client_id=scope.client_id)
        if not result:
            raise HTTPException(status_code=400, detail="Failed to create customers")

        logger.info(f"Customers created successfully with id: {result.id}")
        # Domain webhook (ISSUE-051, H25): notify subscribers of the new customer.
        background_tasks.add_task(
            fire_event_background,
            owner_id,
            "customer.created",
            {"customer_id": result.id, "name": result.name},
        )
        return result
    except ValueError as e:
        logger.error(f"Validation error creating customers: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating customers: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/batch", response_model=List[CustomersResponse], status_code=201)
async def create_customerss_batch(
    request: CustomersBatchCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Create multiple customerss in a single request"""
    logger.debug(f"Batch creating {len(request.items)} customerss")
    
    service = CustomersService(db)
    results = []
    
    try:
        for item_data in request.items:
            result = await service.create(_serialize_tags(item_data.model_dump()), user_id=(scope.owner_user_id or str(current_user.id)), client_id=scope.client_id)
            if result:
                results.append(result)
        
        logger.info(f"Batch created {len(results)} customerss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch create: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch create failed: {str(e)}")


@router.put("/batch", response_model=List[CustomersResponse])
async def update_customerss_batch(
    request: CustomersBatchUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Update multiple customerss in a single request (requires ownership)"""
    logger.debug(f"Batch updating {len(request.items)} customerss")
    
    service = CustomersService(db)
    results = []
    
    try:
        for item in request.items:
            # Only include non-None values for partial updates
            update_dict = {k: v for k, v in item.updates.model_dump().items() if v is not None}
            _serialize_tags(update_dict)  # CRM-04 (F-039)
            result = await service.update(item.id, update_dict, user_id=scope.owner_user_id)
            if result:
                results.append(result)
        
        logger.info(f"Batch updated {len(results)} customerss successfully")
        return results
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch update failed: {str(e)}")


@router.put("/{id}", response_model=CustomersResponse)
async def update_customers(
    id: int,
    data: CustomersUpdateData,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing customers (requires ownership)"""
    logger.debug(f"Updating customers {id} with data: {data}")

    service = CustomersService(db)
    try:
        # Only include non-None values for partial updates
        update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        # PDPL (SEC-05): re-stamp whenever the consent flag is changed (given or
        # withdrawn) so the merchant can evidence the change.
        if "marketing_consent" in update_dict:
            update_dict["consent_updated_at"] = datetime.now()
        # CRM-04 (F-039): a sent ``tags`` list (incl. an empty one to clear) is
        # encoded to the stored JSON string.
        _serialize_tags(update_dict)
        result = await service.update(id, update_dict, user_id=scope.owner_user_id)
        if not result:
            logger.warning(f"Customers with id {id} not found for update")
            raise HTTPException(status_code=404, detail="Customers not found")
        
        logger.info(f"Customers {id} updated successfully")
        return result
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error updating customers {id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating customers {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/batch")
async def delete_customerss_batch(
    request: CustomersBatchDeleteRequest,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple customerss by their IDs (requires ownership)"""
    logger.debug(f"Batch deleting {len(request.ids)} customerss")
    
    service = CustomersService(db)
    deleted_count = 0
    
    try:
        for item_id in request.ids:
            success = await service.delete(item_id, user_id=scope.owner_user_id)
            if success:
                deleted_count += 1
        
        logger.info(f"Batch deleted {deleted_count} customerss successfully")
        return {"message": f"Successfully deleted {deleted_count} customerss", "deleted_count": deleted_count}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in batch delete: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch delete failed: {str(e)}")


@router.delete("/{id}")
async def delete_customers(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Delete a single customers by ID (requires ownership)"""
    logger.debug(f"Deleting customers with id: {id}")
    
    service = CustomersService(db)
    try:
        success = await service.delete(id, user_id=scope.owner_user_id)
        if not success:
            logger.warning(f"Customers with id {id} not found for deletion")
            raise HTTPException(status_code=404, detail="Customers not found")
        
        logger.info(f"Customers {id} deleted successfully")
        return {"message": "Customers deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting customers {id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


# ---------- M5·CRM (#221) — per-customer store-credit ledger ----------
class StoreCreditEntry(BaseModel):
    """One movement row in a customer's store-credit ledger."""
    id: int
    entry_type: str
    amount: float
    balance_after: float
    transaction_id: Optional[int] = None
    note: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class StoreCreditResponse(BaseModel):
    """A customer's current store-credit balance + its movement history."""
    customer_id: int
    balance: float
    history: List[StoreCreditEntry]


class StoreCreditMovementResponse(BaseModel):
    """The result of posting a store-credit movement: new balance + the booked row."""
    customer_id: int
    balance: float
    entry: StoreCreditEntry


class StoreCreditMovementData(BaseModel):
    """Body for granting or redeeming store credit. ``amount`` is a positive
    magnitude; the sign is derived server-side from ``entry_type``."""
    entry_type: str  # grant | redeem | adjust | refund
    amount: float
    note: Optional[str] = None
    transaction_id: Optional[int] = None


async def _owned_customer_or_404(service: CustomersService, customer_id: int, *, user_id):
    """Resolve a customer within the caller's tenancy or 404 (SEC-02)."""
    customer = await service.get_by_id(customer_id, user_id=user_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customers not found")
    return customer


@router.get("/{id}/store-credit", response_model=StoreCreditResponse)
async def get_store_credit(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """A customer's store-credit balance + ledger history (CRM, #221).

    Owner-scoped (SEC-02): a foreign/unknown customer id → 404."""
    await _owned_customer_or_404(CustomersService(db), id, user_id=scope.owner_user_id)
    credit = StoreCreditService(db)
    rows = await credit.history(id, user_id=scope.owner_user_id)
    balance = await credit.balance(id, user_id=scope.owner_user_id)
    return {
        "customer_id": id,
        "balance": float(balance),
        "history": [StoreCreditEntry.model_validate(r) for r in rows],
    }


@router.post("/{id}/store-credit", response_model=StoreCreditMovementResponse, status_code=201)
async def post_store_credit(
    id: int,
    data: StoreCreditMovementData,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Grant or redeem store credit for a customer (CRM, #221).

    The server is authoritative: a redemption is validated against the live balance
    so it can never overdraw (400). Owner-scoped (SEC-02): a foreign customer → 404."""
    await _owned_customer_or_404(CustomersService(db), id, user_id=scope.owner_user_id)
    credit = StoreCreditService(db)
    try:
        row = await credit.post(
            id,
            user_id=scope.owner_user_id,
            client_id=scope.client_id,
            entry_type=data.entry_type,
            amount=data.amount,
            note=data.note,
            transaction_id=data.transaction_id,
        )
    except StoreCreditError as e:
        raise HTTPException(status_code=400, detail=str(e))
    balance = await credit.balance(id, user_id=scope.owner_user_id)
    return {
        "customer_id": id,
        "balance": float(balance),
        "entry": StoreCreditEntry.model_validate(row),
    }


# ---------- M5·CRM (#221) — per-customer notes thread ----------
class CustomerNoteEntry(BaseModel):
    """One note in a customer's append-only thread."""
    id: int
    body: str
    author: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CustomerNotesResponse(BaseModel):
    """A customer's notes thread, newest-first."""
    customer_id: int
    items: List[CustomerNoteEntry]


class CustomerNoteData(BaseModel):
    """Body for appending a note. ``body`` is required and non-blank."""
    body: str
    author: Optional[str] = None


@router.get("/{id}/notes", response_model=CustomerNotesResponse)
async def get_customer_notes(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """A customer's notes thread, newest-first (CRM, #221).

    Owner-scoped (SEC-02): a foreign/unknown customer id → 404."""
    await _owned_customer_or_404(CustomersService(db), id, user_id=scope.owner_user_id)
    rows = await CustomerNotesService(db).list(id, user_id=scope.owner_user_id)
    return {
        "customer_id": id,
        "items": [CustomerNoteEntry.model_validate(r) for r in rows],
    }


@router.post("/{id}/notes", response_model=CustomerNoteEntry, status_code=201)
async def add_customer_note(
    id: int,
    data: CustomerNoteData,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Append a note to a customer's thread (CRM, #221).

    Owner-scoped (SEC-02): a foreign/unknown customer id → 404. A blank body → 400."""
    await _owned_customer_or_404(CustomersService(db), id, user_id=scope.owner_user_id)
    try:
        note = await CustomerNotesService(db).add(
            id,
            user_id=scope.owner_user_id,
            client_id=scope.client_id,
            body=data.body,
            author=data.author,
        )
    except CustomerNoteError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return CustomerNoteEntry.model_validate(note)


# ---------- M5·CRM (#221) — customer blacklist ----------
class BlacklistData(BaseModel):
    """Body for blacklisting a customer; the reason is recorded for the audit trail."""
    reason: Optional[str] = None


@router.post("/{id}/blacklist", response_model=CustomersResponse)
async def blacklist_customer(
    id: int,
    data: BlacklistData,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Blacklist a customer so they can no longer transact (CRM, #221).

    Owner-scoped (SEC-02): a foreign/unknown customer id → 404. The block is
    enforced server-side at sale time (POS), not merely surfaced in the UI."""
    customer = await CustomersService(db).set_blacklist(
        id, user_id=scope.owner_user_id, reason=data.reason
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Customers not found")
    return CustomersResponse.model_validate(customer)


@router.delete("/{id}/blacklist", response_model=CustomersResponse)
async def unblacklist_customer(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Lift a customer's blacklist (CRM, #221). Owner-scoped (SEC-02): foreign → 404."""
    customer = await CustomersService(db).clear_blacklist(id, user_id=scope.owner_user_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customers not found")
    return CustomersResponse.model_validate(customer)


@router.post("/{id}/group", response_model=CustomersResponse)
async def assign_customer_group(
    id: int,
    data: CustomerGroupAssignData,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Assign a customer to one of the merchant's groups (CRM, #221).

    Owner-scoped (SEC-02): a foreign/unknown customer **or** group id → 404."""
    customer = await CustomerGroupsService(db).assign(
        id, data.group_id, user_id=scope.owner_user_id
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Customer or group not found")
    return CustomersResponse.model_validate(customer)


@router.delete("/{id}/group", response_model=CustomersResponse)
async def unassign_customer_group(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    scope: TenantScope = Depends(get_tenant_scope),
    db: AsyncSession = Depends(get_db),
):
    """Remove a customer from their group (CRM, #221). Owner-scoped (SEC-02): foreign → 404."""
    customer = await CustomerGroupsService(db).assign(id, None, user_id=scope.owner_user_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customers not found")
    return CustomersResponse.model_validate(customer)