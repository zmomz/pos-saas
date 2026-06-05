import json
import logging
import hashlib
import base64
import os
import secrets
import struct
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import select, func, update, case, and_
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import get_db
from core.email import send_provisioning_email
from core.security import hash_password
from dependencies.auth import get_current_user
from dependencies.features import FEATURE_KEYS
from schemas.auth import UserResponse
from models.auth import User
from models.agents import Agents
from models.clients import Clients
from models.packages import Packages
from services.packages import parse_feature_tier
from models.products import Products
from models.transactions import Transactions
from models.agent_features import Agent_features
from models.client_features import Client_features
from models.subscription_payments import Subscription_payments
from models.commission_ledger import Commission_ledger
from models.audit_logs import Audit_logs
from services.commission import compute_commission_split
from services.system_settings import (
    GLOBAL_TAX_RATE_KEY,
    get_global_tax_rate,
    set_setting,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/tenant", tags=["tenant"])


def normalize_domain(raw: Optional[str]) -> Optional[str]:
    """Canonicalize a custom domain / Host header for AG-05 matching.

    Lowercases, strips an optional scheme, path, port, leading ``www.`` and a
    trailing dot, so ``https://WWW.Acme.SA:443/login`` and ``acme.sa`` resolve to
    the same stored key. Returns None for empty input (clears the domain).
    """
    if not raw:
        return None
    host = raw.strip().lower()
    if "://" in host:
        host = host.split("://", 1)[1]
    host = host.split("/", 1)[0]
    host = host.split("?", 1)[0]
    host = host.split(":", 1)[0]  # drop port
    host = host.rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    return host or None


def agent_login_url(agent: Agents) -> Optional[str]:
    """The branded login URL for an agent's provisioned merchants (AG-05/AG-06).

    Prefers the agent's custom domain when set, else falls back to the platform
    FRONTEND_URL. Returns None only when neither is configured.
    """
    domain = normalize_domain(getattr(agent, "custom_domain", None))
    if domain:
        return f"https://{domain}/login"
    base = getattr(settings, "frontend_url", None)
    if base:
        return f"{base.rstrip('/')}/login"
    return None


# ---------- Pydantic Schemas ----------
class RoleResponse(BaseModel):
    role: str  # "master", "agent", "client"
    entity_id: Optional[int] = None
    agent_id: Optional[int] = None

class AgentStatsResponse(BaseModel):
    id: int
    company_name: str
    email: str
    phone: Optional[str] = None
    package_type: int
    used_slots: int
    is_active: bool
    primary_color: Optional[str] = None
    created_at: Optional[datetime] = None

class MasterAgentsResponse(BaseModel):
    items: List[AgentStatsResponse]
    total: int

class ClientListItem(BaseModel):
    id: int
    business_name: str
    email: str
    phone: Optional[str] = None
    subscription_fee: Optional[float] = None
    is_active: bool
    zatca_enabled: bool
    language_preference: str
    created_at: Optional[datetime] = None

class AgentClientsResponse(BaseModel):
    items: List[ClientListItem]
    total: int
    remaining_slots: int

class BrandingResponse(BaseModel):
    logo_url: Optional[str] = None
    primary_color: str
    secondary_color: str
    font_family: str
    button_radius: str
    company_name: str
    # Agent-set default UI language; a client loads this on first login unless it
    # has overridden its own preference (L10N-05).
    default_language: str = "en"
    # AG-05: the agent's custom domain (when configured). Surfaced so the front-end
    # can build branded login/funnel URLs. Public-safe (it's the served host).
    custom_domain: Optional[str] = None
    # AG-06: the agent's provisioning-email template. Populated only on the agent's
    # OWN branding read (never leaked to clients / the public by-domain lookup).
    email_template_subject: Optional[str] = None
    email_template_body: Optional[str] = None

class CreateClientRequest(BaseModel):
    business_name: str
    email: str
    phone: Optional[str] = None
    subscription_fee: Optional[float] = 0
    # None ⇒ inherit the agent's default_language (L10N-05). An explicit value is
    # the client overriding that default at creation time.
    language_preference: Optional[str] = None
    # retail / restaurant / both (CL-02). Defaults to retail; drives POS mode and
    # gates the restaurant vertical (RST-*, F-045).
    business_type: Optional[str] = "retail"
    features: Optional[List[str]] = None


class CreateClientResponse(ClientListItem):
    """Returned once on client creation. Carries the one-time temp password the
    merchant uses to log in (force-reset on first login). The credential is never
    stored in plaintext and is only surfaced here / emailed."""

    temp_password: str
    must_change_password: bool = True
    # True when the credentials were actually emailed; False ⇒ surface in the UI.
    email_delivered: bool = False

class DashboardStatsResponse(BaseModel):
    total_sales: float
    total_transactions: int
    today_transactions: int
    today_sales: float
    products_count: int

class ToggleResponse(BaseModel):
    success: bool
    is_active: bool


class CreateAgentRequest(BaseModel):
    company_name: str
    email: str
    phone: Optional[str] = None
    # Either reference a package (its client_slots become the agent's slots) or
    # pass an explicit slot count. package_id wins when both are given.
    package_id: Optional[int] = None
    slots: Optional[int] = None


class CreateAgentResponse(BaseModel):
    id: int
    company_name: str
    email: str
    phone: Optional[str] = None
    package_type: int
    used_slots: int
    is_active: bool
    # One-time temporary password for the agent's login account. The agent must
    # change it on first login. Returned only here, never stored in plaintext.
    temp_password: str


class AddSlotsRequest(BaseModel):
    slots: int  # number of client slots to add (positive)


class SlotsResponse(BaseModel):
    id: int
    package_type: int
    used_slots: int
    remaining_slots: int


class TaxRateResponse(BaseModel):
    tax_rate: float
    is_global: bool  # True when set by master; False when falling back to default


class SetTaxRateRequest(BaseModel):
    tax_rate: float


class FeatureToggleRequest(BaseModel):
    feature_name: str
    is_enabled: bool


class FeatureToggleResponse(BaseModel):
    client_id: int
    feature_name: str
    is_enabled: bool


# ---------- Helper: Determine user role ----------
async def get_user_role(db: AsyncSession, user_id: str) -> dict:
    """Determine user role based on database records"""
    # Check if user is an agent
    result = await db.execute(
        select(Agents).where(Agents.user_id == user_id)
    )
    agent = result.scalar_one_or_none()
    if agent:
        return {"role": "agent", "entity_id": agent.id, "agent_id": None}

    # Check if user is a client
    result = await db.execute(
        select(Clients).where(Clients.user_id == user_id)
    )
    client = result.scalar_one_or_none()
    if client:
        return {"role": "client", "entity_id": client.id, "agent_id": client.agent_id}

    # Only explicitly-seeded admins act as the platform master. Any other
    # account without an agent/client record is treated as a least-privilege
    # client (prevents self-registered users from becoming master).
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if user and user.role == "admin":
        return {"role": "master", "entity_id": None, "agent_id": None}

    return {"role": "client", "entity_id": None, "agent_id": None}


# ---------- Role Detection ----------
@router.get("/role", response_model=RoleResponse)
async def detect_role(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Detect the current user's role in the system"""
    role_info = await get_user_role(db, str(current_user.id))
    return RoleResponse(**role_info)


# ---------- Master Endpoints ----------
@router.get("/master/agents", response_model=MasterAgentsResponse)
async def list_all_agents(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Master: List all agents with stats"""
    role_info = await get_user_role(db, str(current_user.id))
    if role_info["role"] != "master":
        raise HTTPException(status_code=403, detail="Only master can access this endpoint")

    result = await db.execute(
        select(Agents).order_by(Agents.created_at.desc()).offset(skip).limit(limit)
    )
    agents = result.scalars().all()

    count_result = await db.execute(select(func.count(Agents.id)))
    total = count_result.scalar() or 0

    items = []
    for agent in agents:
        items.append(AgentStatsResponse(
            id=agent.id,
            company_name=agent.company_name,
            email=agent.email,
            phone=agent.phone,
            package_type=agent.package_type,
            used_slots=agent.used_slots or 0,
            is_active=agent.is_active if agent.is_active is not None else True,
            primary_color=agent.primary_color,
            created_at=agent.created_at,
        ))

    return MasterAgentsResponse(items=items, total=total)


@router.post("/master/agents/{agent_id}/toggle", response_model=ToggleResponse)
async def toggle_agent(
    agent_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Master: Toggle agent active status"""
    role_info = await get_user_role(db, str(current_user.id))
    if role_info["role"] != "master":
        raise HTTPException(status_code=403, detail="Only master can access this endpoint")

    result = await db.execute(select(Agents).where(Agents.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    new_status = not (agent.is_active if agent.is_active is not None else True)
    await db.execute(
        update(Agents).where(Agents.id == agent_id).values(is_active=new_status)
    )
    await db.commit()

    return ToggleResponse(success=True, is_active=new_status)


@router.post("/master/agents", response_model=CreateAgentResponse, status_code=201)
async def create_agent(
    data: CreateAgentRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Master: create a white-label agent (SRS MA-01).

    Provisions a real login account (email + generated temp password) **and** the
    ``Agents`` row linked to it, so the new agent can sign in immediately and is
    detected as an agent by role resolution. The temp password is returned once.
    """
    role_info = await get_user_role(db, str(current_user.id))
    if role_info["role"] != "master":
        raise HTTPException(status_code=403, detail="Only master can access this endpoint")

    email = data.email.strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")

    # Reject duplicates up-front (clearer than a DB integrity error).
    existing = await db.execute(select(User).where(func.lower(User.email) == email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="A user with this email already exists")

    # Resolve the agent's client-slot allowance and (MA-07) feature tier.
    slots = data.slots or 0
    feature_tier = None  # the package's enabled-feature set, when provisioned from one
    if data.package_id is not None:
        pkg_result = await db.execute(select(Packages).where(Packages.id == data.package_id))
        package = pkg_result.scalar_one_or_none()
        if not package:
            raise HTTPException(status_code=404, detail="Package not found")
        slots = package.client_slots
        feature_tier = parse_feature_tier(package.features)
    if slots <= 0:
        slots = 1  # never provision an agent with zero capacity

    # Create the login account for the agent.
    temp_password = secrets.token_urlsafe(9)
    new_user = User(
        id=str(uuid.uuid4()),
        email=email,
        name=data.company_name,
        hashed_password=hash_password(temp_password),
        role="user",  # tier is derived from the Agents row, not this column
        last_login=None,
    )
    db.add(new_user)

    new_agent = Agents(
        user_id=new_user.id,
        company_name=data.company_name,
        email=email,
        phone=data.phone,
        package_type=slots,
        package_id=data.package_id,  # MA-07: retain the package link for tier derivation
        used_slots=0,
        is_active=True,
    )
    db.add(new_agent)
    await db.commit()
    await db.refresh(new_agent)

    # MA-07: seed the agent's feature entitlements from the package tier. A feature
    # is enabled-by-default, so the tier is applied by explicitly DISABLING every
    # canonical key the package does not unlock; keys in the tier stay enabled.
    if feature_tier is not None:
        enabled = set(feature_tier)
        for key in sorted(FEATURE_KEYS):
            db.add(
                Agent_features(
                    user_id=new_user.id,
                    agent_id=new_agent.id,
                    feature_name=key,
                    is_enabled_default=(key in enabled),
                )
            )
        await db.commit()

    return CreateAgentResponse(
        id=new_agent.id,
        company_name=new_agent.company_name,
        email=new_agent.email,
        phone=new_agent.phone,
        package_type=new_agent.package_type,
        used_slots=new_agent.used_slots or 0,
        is_active=True,
        temp_password=temp_password,
    )


@router.post("/master/agents/{agent_id}/slots", response_model=SlotsResponse)
async def add_agent_slots(
    agent_id: int,
    data: AddSlotsRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Master: add client slots to an agent's package (SRS MA-04)."""
    role_info = await get_user_role(db, str(current_user.id))
    if role_info["role"] != "master":
        raise HTTPException(status_code=403, detail="Only master can access this endpoint")

    if data.slots <= 0:
        raise HTTPException(status_code=400, detail="slots must be a positive integer")

    result = await db.execute(select(Agents).where(Agents.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    new_total = (agent.package_type or 0) + data.slots
    await db.execute(
        update(Agents).where(Agents.id == agent_id).values(package_type=new_total)
    )
    await db.commit()

    used = agent.used_slots or 0
    return SlotsResponse(
        id=agent_id,
        package_type=new_total,
        used_slots=used,
        remaining_slots=new_total - used,
    )


# ---------- Global tax rate (MA-05) ----------
@router.get("/tax-rate", response_model=TaxRateResponse)
async def get_tax_rate(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Any authenticated user: read the effective global VAT rate.

    Agents and clients inherit the master's rate and cannot override it.
    """
    global_rate = await get_global_tax_rate(db)
    if global_rate is not None:
        return TaxRateResponse(tax_rate=global_rate, is_global=True)
    return TaxRateResponse(tax_rate=15.0, is_global=False)


@router.put("/master/tax-rate", response_model=TaxRateResponse)
async def set_tax_rate(
    data: SetTaxRateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Master: set the global VAT rate inherited by all agents/clients (MA-05)."""
    role_info = await get_user_role(db, str(current_user.id))
    if role_info["role"] != "master":
        raise HTTPException(status_code=403, detail="Only master can set the global tax rate")

    if data.tax_rate < 0 or data.tax_rate > 100:
        raise HTTPException(status_code=400, detail="tax_rate must be between 0 and 100")

    await set_setting(db, GLOBAL_TAX_RATE_KEY, str(data.tax_rate))
    await db.commit()
    return TaxRateResponse(tax_rate=data.tax_rate, is_global=True)


# ---------- Agent Endpoints ----------
@router.get("/agent/clients", response_model=AgentClientsResponse)
async def list_agent_clients(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Agent: List their clients"""
    role_info = await get_user_role(db, str(current_user.id))
    if role_info["role"] != "agent":
        raise HTTPException(status_code=403, detail="Only agents can access this endpoint")

    agent_id = role_info["entity_id"]

    # Get agent for slot info
    agent_result = await db.execute(select(Agents).where(Agents.id == agent_id))
    agent = agent_result.scalar_one_or_none()

    result = await db.execute(
        select(Clients).where(Clients.agent_id == agent_id)
        .order_by(Clients.created_at.desc()).offset(skip).limit(limit)
    )
    clients = result.scalars().all()

    count_result = await db.execute(
        select(func.count(Clients.id)).where(Clients.agent_id == agent_id)
    )
    total = count_result.scalar() or 0

    remaining_slots = (agent.package_type or 0) - (agent.used_slots or 0)

    items = []
    for client in clients:
        items.append(ClientListItem(
            id=client.id,
            business_name=client.business_name,
            email=client.email,
            phone=client.phone,
            subscription_fee=client.subscription_fee,
            is_active=client.is_active if client.is_active is not None else True,
            zatca_enabled=client.zatca_enabled if client.zatca_enabled is not None else True,
            language_preference=client.language_preference or "en",
            created_at=client.created_at,
        ))

    return AgentClientsResponse(items=items, total=total, remaining_slots=remaining_slots)


# ---------- Agent revenue / commission (RSL-01/02, F-029) ----------
class RevenueByClient(BaseModel):
    client_id: int
    business_name: str
    collected: float
    master_owed: float
    net: float
    payments: int


class AgentRevenueResponse(BaseModel):
    """The agent's settled-subscription economics, summed from the commission
    ledger. ``collected`` is gross fees taken, ``master_owed`` the platform's cut
    (per-client wholesale), ``net`` the agent's margin; ``collected ==
    master_owed + net`` by construction."""

    collected: float
    master_owed: float
    net: float
    payments: int
    by_client: List[RevenueByClient] = []


@router.get("/agent/revenue", response_model=AgentRevenueResponse)
async def get_agent_revenue(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Agent: revenue / commission summary from the split ledger (RSL-01/02).

    Aggregated in SQL (no load-everything, OPS-05) and scoped to the caller's own
    agent rows — one agent can never see another agent's revenue (SEC-02). A
    client/master gets 403. The master economics rollup (MA-08/RSL-08) is F-023.
    """
    role_info = await get_user_role(db, str(current_user.id))
    if role_info["role"] != "agent":
        raise HTTPException(status_code=403, detail="Only agents can access this endpoint")

    agent_id = role_info["entity_id"]

    totals = (
        await db.execute(
            select(
                func.coalesce(func.sum(Commission_ledger.gross), 0.0),
                func.coalesce(func.sum(Commission_ledger.master_cut), 0.0),
                func.coalesce(func.sum(Commission_ledger.agent_net), 0.0),
                func.count(Commission_ledger.id),
            ).where(Commission_ledger.agent_id == agent_id)
        )
    ).one()

    per_client_rows = (
        await db.execute(
            select(
                Commission_ledger.client_id,
                func.coalesce(func.sum(Commission_ledger.gross), 0.0),
                func.coalesce(func.sum(Commission_ledger.master_cut), 0.0),
                func.coalesce(func.sum(Commission_ledger.agent_net), 0.0),
                func.count(Commission_ledger.id),
            )
            .where(Commission_ledger.agent_id == agent_id)
            .group_by(Commission_ledger.client_id)
        )
    ).all()

    # Resolve business names for the client breakdown (small set — one query).
    names: dict = {}
    if per_client_rows:
        client_ids = [r[0] for r in per_client_rows]
        for cid, bname in (
            await db.execute(
                select(Clients.id, Clients.business_name).where(Clients.id.in_(client_ids))
            )
        ).all():
            names[cid] = bname

    by_client = [
        RevenueByClient(
            client_id=cid,
            business_name=names.get(cid, ""),
            collected=round(float(collected or 0), 2),
            master_owed=round(float(master_owed or 0), 2),
            net=round(float(net or 0), 2),
            payments=int(cnt or 0),
        )
        for cid, collected, master_owed, net, cnt in per_client_rows
    ]

    return AgentRevenueResponse(
        collected=round(float(totals[0] or 0), 2),
        master_owed=round(float(totals[1] or 0), 2),
        net=round(float(totals[2] or 0), 2),
        payments=int(totals[3] or 0),
        by_client=by_client,
    )


# ---------- Master platform economics (MA-08 / RSL-08 / RPT-09, F-023) ----------
class AgentEconomics(BaseModel):
    """One agent's contribution to the platform economics rollup (the master's
    revenue-by-agent leaderboard). ``collected`` is gross subscription fees the
    agent took from its merchants, ``master_owed`` the platform's share (the sum
    of the commission ledger's ``master_cut``), ``net`` the agent's margin; ``mrr``
    is the agent's normalized monthly recurring revenue across its active clients."""

    agent_id: int
    company_name: str
    is_active: bool
    total_clients: int
    active_clients: int
    mrr: float
    collected: float
    master_owed: float
    net: float
    payments: int


class MasterEconomicsResponse(BaseModel):
    """Platform-wide economics for the master operator console (MA-08).

    ``mrr`` is the normalized **monthly** recurring revenue across all non-suspended
    active client subscriptions (a yearly plan contributes ``fee/12``); ``arr`` is
    ``mrr * 12``. ``churn_rate`` is the share of client subscriptions currently
    suspended (``churned_clients / total_clients``) — the only churn signal
    derivable without a cancellation-timestamp history. ``collected`` is gross fees
    settled platform-wide and ``platform_revenue`` the master's owed cut (sum of the
    commission ledger's ``master_cut``). ``by_agent`` is the revenue-by-agent
    leaderboard (RSL-08)."""

    total_agents: int
    active_agents: int
    total_clients: int
    active_clients: int
    churned_clients: int
    mrr: float
    arr: float
    churn_rate: float
    collected: float
    platform_revenue: float
    by_agent: List[AgentEconomics] = []


@router.get("/master/economics", response_model=MasterEconomicsResponse)
async def get_master_economics(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Master: platform-wide economics — MRR, churn, active merchants, and the
    revenue-by-agent leaderboard (MA-08 / RSL-08 / RPT-09).

    Everything is aggregated in SQL (no load-everything, OPS-05). Restricted to the
    platform master; an agent/client gets 403 (SEC-02 — only the operator sees
    cross-tenant economics). MRR normalizes a yearly plan to ``fee/12`` and counts
    only non-suspended active subscriptions; churn is the suspended share.
    """
    role_info = await get_user_role(db, str(current_user.id))
    if role_info["role"] != "master":
        raise HTTPException(status_code=403, detail="Only master can access this endpoint")

    # A client subscription is "live" (counts toward MRR) when its row is active and
    # not suspended; a NULL status is treated as the default 'active'. A yearly plan
    # contributes 1/12 of its fee to the monthly figure.
    status_expr = func.coalesce(Clients.subscription_status, "active")
    active_pred = and_(Clients.is_active.isnot(False), status_expr != "suspended")
    suspended_pred = status_expr == "suspended"
    monthly_fee = case(
        (Clients.billing_cycle == "yearly", func.coalesce(Clients.subscription_fee, 0.0) / 12.0),
        else_=func.coalesce(Clients.subscription_fee, 0.0),
    )

    # Platform totals — authoritative (counts even orphan-agent clients).
    plat = (
        await db.execute(
            select(
                func.count(Clients.id),
                func.coalesce(func.sum(case((active_pred, 1), else_=0)), 0),
                func.coalesce(func.sum(case((suspended_pred, 1), else_=0)), 0),
                func.coalesce(func.sum(case((active_pred, monthly_fee), else_=0.0)), 0.0),
            )
        )
    ).one()
    total_clients = int(plat[0] or 0)
    active_clients = int(plat[1] or 0)
    churned_clients = int(plat[2] or 0)
    mrr = round(float(plat[3] or 0.0), 2)

    plat_ledger = (
        await db.execute(
            select(
                func.coalesce(func.sum(Commission_ledger.gross), 0.0),
                func.coalesce(func.sum(Commission_ledger.master_cut), 0.0),
            )
        )
    ).one()
    collected = round(float(plat_ledger[0] or 0.0), 2)
    platform_revenue = round(float(plat_ledger[1] or 0.0), 2)

    churn_rate = round(churned_clients / total_clients, 4) if total_clients else 0.0

    # Per-agent breakdown (leaderboard): client counts/MRR by agent + ledger by agent.
    client_rows = (
        await db.execute(
            select(
                Clients.agent_id,
                func.count(Clients.id),
                func.coalesce(func.sum(case((active_pred, 1), else_=0)), 0),
                func.coalesce(func.sum(case((active_pred, monthly_fee), else_=0.0)), 0.0),
            ).group_by(Clients.agent_id)
        )
    ).all()
    clients_by_agent = {r[0]: r for r in client_rows}

    ledger_rows = (
        await db.execute(
            select(
                Commission_ledger.agent_id,
                func.coalesce(func.sum(Commission_ledger.gross), 0.0),
                func.coalesce(func.sum(Commission_ledger.master_cut), 0.0),
                func.coalesce(func.sum(Commission_ledger.agent_net), 0.0),
                func.count(Commission_ledger.id),
            ).group_by(Commission_ledger.agent_id)
        )
    ).all()
    ledger_by_agent = {r[0]: r for r in ledger_rows}

    agents = (await db.execute(select(Agents).order_by(Agents.created_at.desc()))).scalars().all()
    active_agents = sum(1 for a in agents if a.is_active is not False)

    by_agent: List[AgentEconomics] = []
    for ag in agents:
        c = clients_by_agent.get(ag.id)
        l = ledger_by_agent.get(ag.id)
        by_agent.append(
            AgentEconomics(
                agent_id=ag.id,
                company_name=ag.company_name,
                is_active=ag.is_active if ag.is_active is not None else True,
                total_clients=int(c[1]) if c else 0,
                active_clients=int(c[2]) if c else 0,
                mrr=round(float(c[3]) if c else 0.0, 2),
                collected=round(float(l[1]) if l else 0.0, 2),
                master_owed=round(float(l[2]) if l else 0.0, 2),
                net=round(float(l[3]) if l else 0.0, 2),
                payments=int(l[4]) if l else 0,
            )
        )

    return MasterEconomicsResponse(
        total_agents=len(agents),
        active_agents=active_agents,
        total_clients=total_clients,
        active_clients=active_clients,
        churned_clients=churned_clients,
        mrr=mrr,
        arr=round(mrr * 12, 2),
        churn_rate=churn_rate,
        collected=collected,
        platform_revenue=platform_revenue,
        by_agent=by_agent,
    )


@router.get("/agent/branding", response_model=BrandingResponse)
async def get_agent_branding(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Agent: Get own branding config"""
    role_info = await get_user_role(db, str(current_user.id))
    if role_info["role"] != "agent":
        raise HTTPException(status_code=403, detail="Only agents can access this endpoint")

    result = await db.execute(select(Agents).where(Agents.id == role_info["entity_id"]))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    return BrandingResponse(
        logo_url=agent.logo_url,
        primary_color=agent.primary_color or "#3B82F6",
        secondary_color=agent.secondary_color or "#1E40AF",
        font_family=agent.font_family or "Inter",
        button_radius=agent.button_radius or "8px",
        company_name=agent.company_name,
        default_language=agent.default_language or "en",
        # The agent's own read exposes the white-label settings it manages.
        custom_domain=getattr(agent, "custom_domain", None),
        email_template_subject=getattr(agent, "email_template_subject", None),
        email_template_body=getattr(agent, "email_template_body", None),
    )


@router.get("/branding/by-domain", response_model=BrandingResponse)
async def get_branding_by_domain(
    domain: str = Query(..., description="The host the request arrived on (AG-05)"),
    db: AsyncSession = Depends(get_db),
):
    """Public: resolve an agent's branding from a custom domain (AG-05).

    Unauthenticated by design — the merchant login + funnel are served on the
    agent's own domain *before* anyone signs in, so the front-end resolves the
    brand from ``window.location.host`` here. Returns 404 when no agent claims the
    domain (the caller falls back to the platform default theme). The agent's email
    template is never exposed on this public path.
    """
    normalized = normalize_domain(domain)
    if not normalized:
        raise HTTPException(status_code=404, detail="No branding for this domain")

    result = await db.execute(
        select(Agents).where(
            func.lower(Agents.custom_domain) == normalized, Agents.is_active == True  # noqa: E712
        )
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="No branding for this domain")

    return BrandingResponse(
        logo_url=agent.logo_url,
        primary_color=agent.primary_color or "#3B82F6",
        secondary_color=agent.secondary_color or "#1E40AF",
        font_family=agent.font_family or "Inter",
        button_radius=agent.button_radius or "8px",
        company_name=agent.company_name,
        default_language=agent.default_language or "en",
        custom_domain=getattr(agent, "custom_domain", None),
        # email_template_* deliberately omitted — not public.
    )


# Agent logo upload (AG-01). Stored locally and served from /uploads; the cloud
# bucket path (routers/storage.py) remains available for S3-backed deployments.
_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOGO_DIR = os.path.join(_BACKEND_ROOT, "uploads", "logos")
_ALLOWED_LOGO_TYPES = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/webp": "webp",
    "image/svg+xml": "svg",
}
_MAX_LOGO_BYTES = 2 * 1024 * 1024  # 2 MB


class LogoUploadResponse(BaseModel):
    logo_url: str


@router.post("/agent/logo", response_model=LogoUploadResponse)
async def upload_agent_logo(
    file: UploadFile = File(...),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Agent: upload a white-label logo (AG-01).

    Validates the MIME type (png/jpeg/webp/svg) and a 2 MB size cap, stores the
    file under ``uploads/logos/``, and persists the served URL on the agent so
    every client of that agent picks up the new logo via the branding endpoint.
    """
    role_info = await get_user_role(db, str(current_user.id))
    if role_info["role"] != "agent":
        raise HTTPException(status_code=403, detail="Only agents can upload a logo")

    ext = _ALLOWED_LOGO_TYPES.get((file.content_type or "").lower())
    if not ext:
        raise HTTPException(
            status_code=400,
            detail="Unsupported image type. Use PNG, JPEG, WebP, or SVG.",
        )

    contents = await file.read()
    if len(contents) > _MAX_LOGO_BYTES:
        raise HTTPException(status_code=413, detail="Logo exceeds the 2 MB size limit")
    if not contents:
        raise HTTPException(status_code=400, detail="Empty file")

    os.makedirs(_LOGO_DIR, exist_ok=True)
    filename = f"agent-{role_info['entity_id']}-{secrets.token_hex(6)}.{ext}"
    with open(os.path.join(_LOGO_DIR, filename), "wb") as fh:
        fh.write(contents)

    logo_url = f"/uploads/logos/{filename}"
    await db.execute(
        update(Agents).where(Agents.id == role_info["entity_id"]).values(logo_url=logo_url)
    )
    await db.commit()
    return LogoUploadResponse(logo_url=logo_url)


@router.post("/agent/clients", response_model=CreateClientResponse)
async def create_client_for_agent(
    data: CreateClientRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Agent: provision a new client merchant (SRS CL-01, deducts a slot).

    Creates a **real login account** for the merchant (own email + generated temp
    password, force-reset on first login) and links ``Clients.user_id`` to that
    new user — NOT the agent — so the merchant can sign in and suspension (CL-05)
    targets the correct account. The slot is deducted atomically (MA-02) so
    concurrent creates cannot oversell a package.
    """
    role_info = await get_user_role(db, str(current_user.id))
    if role_info["role"] != "agent":
        raise HTTPException(status_code=403, detail="Only agents can access this endpoint")

    agent_id = role_info["entity_id"]

    email = (data.email or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")

    agent_result = await db.execute(select(Agents).where(Agents.id == agent_id))
    agent = agent_result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Reject duplicate accounts up-front (clearer than a DB integrity error).
    existing = await db.execute(select(User).where(func.lower(User.email) == email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="A user with this email already exists")

    # MA-02: atomic slot deduction. The guarded UPDATE only succeeds while a slot
    # is free; rowcount==0 means the package is full (or lost a concurrent race).
    slot_result = await db.execute(
        update(Agents)
        .where(
            Agents.id == agent_id,
            func.coalesce(Agents.used_slots, 0) < Agents.package_type,
        )
        .values(used_slots=func.coalesce(Agents.used_slots, 0) + 1)
    )
    if slot_result.rowcount == 0:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="No available client slots. Please upgrade your package.",
        )

    # Create the merchant's login account.
    temp_password = secrets.token_urlsafe(9)
    new_user = User(
        id=str(uuid.uuid4()),
        email=email,
        name=data.business_name,
        hashed_password=hash_password(temp_password),
        role="user",  # tier is derived from the Clients row, not this column
        must_change_password=True,
        last_login=None,
    )
    db.add(new_user)

    # When the agent doesn't pick a language, the client inherits the agent's
    # default language (L10N-05).
    client_language = data.language_preference or agent.default_language or "en"
    # CL-02: business type drives retail vs restaurant POS mode (RST-*). Reject
    # an unknown value up-front rather than silently defaulting.
    business_type = (data.business_type or "retail").strip().lower()
    if business_type not in ("retail", "restaurant", "both"):
        await db.rollback()
        raise HTTPException(
            status_code=400,
            detail="business_type must be one of: retail, restaurant, both",
        )
    new_client = Clients(
        user_id=new_user.id,  # the merchant's own account, NOT the agent's
        agent_id=agent_id,
        business_name=data.business_name,
        email=email,
        phone=data.phone,
        subscription_fee=data.subscription_fee or 0,
        is_active=True,
        language_preference=client_language,
        business_type=business_type,
        # ZA-09: ZATCA is the Saudi default — a new merchant is provisioned with
        # e-invoicing ON. The agent can switch it off later for a non-VAT-registered
        # client (POST /agent/clients/{id}/zatca).
        zatca_enabled=True,
        invoice_counter=0,
    )
    db.add(new_client)

    # Slot decrement + user + client all commit together; any failure above the
    # commit rolls back the slot decrement too.
    await db.commit()
    await db.refresh(new_client)

    # Create default features for client. An explicit feature list from the agent
    # wins (legacy behaviour); otherwise (MA-07) the client inherits the agent's
    # package feature tier — every canonical key outside the tier is explicitly
    # disabled (features are enabled-by-default, so only an is_enabled=False row
    # gates them), so the package actually unlocks the capabilities it advertises.
    if data.features:
        for feature in data.features:
            cf = Client_features(
                user_id=new_user.id,
                client_id=new_client.id,
                feature_name=feature,
                is_enabled=True,
            )
            db.add(cf)
        await db.commit()
    else:
        tier = None
        if getattr(agent, "package_id", None):
            pkg_result = await db.execute(
                select(Packages).where(Packages.id == agent.package_id)
            )
            pkg = pkg_result.scalar_one_or_none()
            tier = parse_feature_tier(pkg.features) if pkg else None
        if tier is not None:
            enabled = set(tier)
            for key in sorted(FEATURE_KEYS):
                db.add(
                    Client_features(
                        user_id=new_user.id,
                        client_id=new_client.id,
                        feature_name=key,
                        is_enabled=(key in enabled),
                    )
                )
            await db.commit()

    # Hand over the credential: email it when SMTP is configured, otherwise the
    # agent surfaces it from the response (dev/no-SMTP). AG-06: the email carries
    # the agent's brand + login URL (their custom domain when set), not the
    # platform identity.
    email_delivered = await send_provisioning_email(
        to_email=email,
        business_name=data.business_name,
        temp_password=temp_password,
        brand_name=agent.company_name,
        login_url=agent_login_url(agent),
        subject_template=getattr(agent, "email_template_subject", None),
        body_template=getattr(agent, "email_template_body", None),
    )

    return CreateClientResponse(
        id=new_client.id,
        business_name=new_client.business_name,
        email=new_client.email,
        phone=new_client.phone,
        subscription_fee=new_client.subscription_fee,
        is_active=True,
        zatca_enabled=True,
        language_preference=new_client.language_preference or "en",
        created_at=new_client.created_at,
        temp_password=temp_password,
        must_change_password=True,
        email_delivered=email_delivered,
    )


@router.post("/agent/clients/{client_id}/toggle", response_model=ToggleResponse)
async def toggle_client(
    client_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Agent: suspend/reactivate one of their own clients (SRS CL-05).

    A suspended client (``is_active = False``) is blocked at authentication by
    ``dependencies/auth.py`` — enforcing non-payment suspension.
    """
    role_info = await get_user_role(db, str(current_user.id))
    if role_info["role"] != "agent":
        raise HTTPException(status_code=403, detail="Only agents can access this endpoint")

    result = await db.execute(
        select(Clients).where(
            Clients.id == client_id, Clients.agent_id == role_info["entity_id"]
        )
    )
    merchant = result.scalar_one_or_none()
    if not merchant:
        raise HTTPException(status_code=404, detail="Client not found")

    new_status = not (merchant.is_active if merchant.is_active is not None else True)
    await db.execute(
        update(Clients).where(Clients.id == client_id).values(is_active=new_status)
    )
    await db.commit()
    return ToggleResponse(success=True, is_active=new_status)


class ZatcaToggleResponse(BaseModel):
    success: bool
    zatca_enabled: bool


@router.post("/agent/clients/{client_id}/zatca", response_model=ZatcaToggleResponse)
async def toggle_client_zatca(
    client_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Agent: turn ZATCA e-invoicing on/off for one of their own clients (ZA-09).

    Makes the per-client ``zatca_enabled`` policy explicit and intentional: when
    on (the Saudi default) every sale is ECDSA-stamped/chained/archived; when off
    a non-VAT-registered merchant's sales complete as simplified non-tax receipts
    with no fiscal document. The sale path honors this via
    ``services/zatca_sale.py::is_zatca_enabled``. Scoped to the agent's own
    clients exactly like :func:`toggle_client` — a non-owning agent gets 404
    (SEC-02). A NULL flag (legacy, de-facto always-signed) reads as enabled, so
    the first toggle switches it off.
    """
    role_info = await get_user_role(db, str(current_user.id))
    if role_info["role"] != "agent":
        raise HTTPException(status_code=403, detail="Only agents can access this endpoint")

    result = await db.execute(
        select(Clients).where(
            Clients.id == client_id, Clients.agent_id == role_info["entity_id"]
        )
    )
    merchant = result.scalar_one_or_none()
    if not merchant:
        raise HTTPException(status_code=404, detail="Client not found")

    new_value = not (merchant.zatca_enabled is not False)
    await db.execute(
        update(Clients).where(Clients.id == client_id).values(zatca_enabled=new_value)
    )
    await db.commit()
    return ZatcaToggleResponse(success=True, zatca_enabled=new_value)


class ResetClientPasswordResponse(BaseModel):
    success: bool
    client_id: int
    email: str
    temp_password: str
    must_change_password: bool
    email_delivered: bool


@router.post(
    "/agent/clients/{client_id}/reset-password",
    response_model=ResetClientPasswordResponse,
)
async def reset_client_password(
    client_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Agent: reset the password of one of their own client merchants (SRS RSL-06).

    Reseller-grade support: when a merchant is locked out, the **owning** agent
    issues a fresh one-time password (force-reset on next login) without the
    platform master being involved. Scoped to the agent's own clients exactly like
    :func:`toggle_client` — a non-owning agent gets 404 (SEC-02). The new password
    targets the merchant's **own** login account (``Clients.user_id``), never the
    agent's. The credential is emailed when SMTP is configured and is always
    surfaced in the response for the agent to relay; only the bcrypt hash is
    stored (never plaintext). The reset is recorded in the audit log.
    """
    role_info = await get_user_role(db, str(current_user.id))
    if role_info["role"] != "agent":
        raise HTTPException(status_code=403, detail="Only agents can access this endpoint")

    result = await db.execute(
        select(Clients).where(
            Clients.id == client_id, Clients.agent_id == role_info["entity_id"]
        )
    )
    merchant = result.scalar_one_or_none()
    if not merchant:
        raise HTTPException(status_code=404, detail="Client not found")

    # The merchant's own login account — NOT the agent's.
    user_result = await db.execute(select(User).where(User.id == merchant.user_id))
    merchant_user = user_result.scalar_one_or_none()
    if not merchant_user:
        raise HTTPException(status_code=404, detail="Client login account not found")

    # Generate + store only the bcrypt hash; force a change on next login.
    temp_password = secrets.token_urlsafe(9)
    await db.execute(
        update(User)
        .where(User.id == merchant.user_id)
        .values(
            hashed_password=hash_password(temp_password),
            must_change_password=True,
        )
    )
    # Security trail (RSL-06): who reset which client. The password is not stored.
    db.add(
        Audit_logs(
            user_id=str(current_user.id),
            action="AGENT_RESET_CLIENT_PASSWORD",
            entity_type="clients",
            entity_id=str(client_id),
            details=(
                f"Agent {role_info['entity_id']} reset the login password "
                f"for client {client_id} ({merchant.email})"
            ),
        )
    )
    await db.commit()

    # Hand over the credential: email it when SMTP is configured, otherwise the
    # agent surfaces it from the response (dev/no-SMTP). AG-06: brand the email
    # with the owning agent's identity + login URL.
    agent = (
        await db.execute(select(Agents).where(Agents.id == role_info["entity_id"]))
    ).scalar_one_or_none()
    email_delivered = await send_provisioning_email(
        to_email=merchant.email,
        business_name=merchant.business_name,
        temp_password=temp_password,
        brand_name=getattr(agent, "company_name", None),
        login_url=agent_login_url(agent) if agent else None,
        subject_template=getattr(agent, "email_template_subject", None),
        body_template=getattr(agent, "email_template_body", None),
    )

    return ResetClientPasswordResponse(
        success=True,
        client_id=client_id,
        email=merchant.email,
        temp_password=temp_password,
        must_change_password=True,
        email_delivered=email_delivered,
    )


@router.post("/agent/clients/{client_id}/features", response_model=FeatureToggleResponse)
async def set_client_feature(
    client_id: int,
    data: FeatureToggleRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Agent: enable/disable a feature for one of their clients at runtime (AG-03).

    The flag is enforced by ``dependencies/features.require_feature`` on gated
    routes. Upserts the ``client_features`` row.
    """
    role_info = await get_user_role(db, str(current_user.id))
    if role_info["role"] != "agent":
        raise HTTPException(status_code=403, detail="Only agents can access this endpoint")

    # AG-03: reject an unknown feature name rather than silently storing a cosmetic
    # switch that gates nothing. Only the enumerated keys (IB §3.2) are togglable.
    if data.feature_name not in FEATURE_KEYS:
        raise HTTPException(
            status_code=400,
            detail=f"feature_name must be one of: {', '.join(sorted(FEATURE_KEYS))}",
        )

    result = await db.execute(
        select(Clients).where(
            Clients.id == client_id, Clients.agent_id == role_info["entity_id"]
        )
    )
    merchant = result.scalar_one_or_none()
    if not merchant:
        raise HTTPException(status_code=404, detail="Client not found")

    existing = await db.execute(
        select(Client_features).where(
            Client_features.client_id == client_id,
            Client_features.feature_name == data.feature_name,
        )
    )
    row = existing.scalar_one_or_none()
    if row is None:
        db.add(
            Client_features(
                user_id=merchant.user_id,
                client_id=client_id,
                feature_name=data.feature_name,
                is_enabled=data.is_enabled,
            )
        )
    else:
        row.is_enabled = data.is_enabled
    await db.commit()

    return FeatureToggleResponse(
        client_id=client_id,
        feature_name=data.feature_name,
        is_enabled=data.is_enabled,
    )


# ---------- Client Endpoints ----------
@router.get("/client/branding", response_model=BrandingResponse)
async def get_client_branding(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Client: Get the agent's branding for this client"""
    role_info = await get_user_role(db, str(current_user.id))
    if role_info["role"] != "client":
        raise HTTPException(status_code=403, detail="Only clients can access this endpoint")

    # Get the agent who owns this client
    result = await db.execute(
        select(Agents).where(Agents.id == role_info["agent_id"])
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    return BrandingResponse(
        logo_url=agent.logo_url,
        primary_color=agent.primary_color or "#3B82F6",
        secondary_color=agent.secondary_color or "#1E40AF",
        font_family=agent.font_family or "Inter",
        button_radius=agent.button_radius or "8px",
        company_name=agent.company_name,
        default_language=agent.default_language or "en",
        custom_domain=getattr(agent, "custom_domain", None),
        # email_template_* deliberately omitted — a client never sees it.
    )


# ---------- Subscription (CL-03 / CL-04) ----------
class SubscriptionPaymentItem(BaseModel):
    id: int
    amount: float
    billing_cycle: Optional[str] = None
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    method: Optional[str] = None
    created_at: Optional[datetime] = None


class SubscriptionResponse(BaseModel):
    client_id: int
    business_name: str
    subscription_fee: float
    billing_cycle: str
    subscription_status: str
    next_billing_date: Optional[str] = None
    is_active: bool
    # Dunning state (CL-06): the consecutive failed-charge counter and the grace
    # deadline drive the client-facing PRN-09 overdue notice.
    dunning_attempts: int = 0
    grace_deadline: Optional[str] = None
    payments: List[SubscriptionPaymentItem] = []


class UpdateSubscriptionRequest(BaseModel):
    subscription_fee: Optional[float] = None
    billing_cycle: Optional[str] = None  # 'monthly' | 'yearly'


def _advance_billing_date(start: datetime, cycle: str) -> str:
    """Return the next billing date (ISO date) one cycle after ``start``."""
    days = 365 if (cycle or "monthly") == "yearly" else 30
    return (start + timedelta(days=days)).date().isoformat()


async def _client_for_current_user(db: AsyncSession, user_id: str) -> Clients:
    result = await db.execute(select(Clients).where(Clients.user_id == str(user_id)))
    merchant = result.scalar_one_or_none()
    if not merchant:
        raise HTTPException(status_code=403, detail="Only clients have a subscription")
    return merchant


async def _subscription_payload(db: AsyncSession, merchant: Clients) -> SubscriptionResponse:
    rows = (
        await db.execute(
            select(Subscription_payments)
            .where(Subscription_payments.client_id == merchant.id)
            .order_by(Subscription_payments.id.desc())
            .limit(24)
        )
    ).scalars().all()
    return SubscriptionResponse(
        client_id=merchant.id,
        business_name=merchant.business_name,
        subscription_fee=merchant.subscription_fee or 0,
        billing_cycle=merchant.billing_cycle or "monthly",
        subscription_status=merchant.subscription_status or "active",
        next_billing_date=merchant.next_billing_date,
        is_active=merchant.is_active if merchant.is_active is not None else True,
        dunning_attempts=int(merchant.dunning_attempts or 0),
        grace_deadline=merchant.grace_deadline,
        payments=[
            SubscriptionPaymentItem(
                id=p.id,
                amount=p.amount,
                billing_cycle=p.billing_cycle,
                period_start=p.period_start,
                period_end=p.period_end,
                method=p.method,
                created_at=p.created_at,
            )
            for p in rows
        ],
    )


@router.get("/client/subscription", response_model=SubscriptionResponse)
async def get_client_subscription(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Client: own subscription status, next billing date, and payment history (CL-04)."""
    merchant = await _client_for_current_user(db, str(current_user.id))
    return await _subscription_payload(db, merchant)


@router.post("/client/subscription/pay", response_model=SubscriptionResponse)
async def pay_client_subscription(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Client: pay the current subscription period (CL-04).

    Records a payment in the ledger, advances ``next_billing_date`` by one
    billing cycle, and marks the subscription active. (Stripe Connect via the
    agent's gateway is the production path; this records the settled payment.)
    """
    merchant = await _client_for_current_user(db, str(current_user.id))
    fee = merchant.subscription_fee or 0
    if fee <= 0:
        raise HTTPException(status_code=400, detail="No subscription fee is configured")

    now = datetime.now(timezone.utc)
    cycle = merchant.billing_cycle or "monthly"
    period_start = now.date().isoformat()
    period_end = _advance_billing_date(now, cycle)

    # CL-04: charge through the agent's Stripe Connect gateway when Stripe is
    # configured; otherwise fall open to a manually-settled record. A real card
    # decline aborts the payment (402) and does NOT advance the billing period.
    from services.subscription_billing import (
        SubscriptionChargeError,
        charge_subscription,
        record_settled_payment,
    )

    agent_stripe_account = None
    agent_row = (
        await db.execute(select(Agents).where(Agents.id == merchant.agent_id))
    ).scalar_one_or_none()
    if agent_row is not None:
        agent_stripe_account = getattr(agent_row, "stripe_account_id", None)

    from core.config import settings as _settings

    try:
        charge = await charge_subscription(
            amount=float(fee),
            currency=str(getattr(_settings, "subscription_currency", "sar") or "sar"),
            agent_stripe_account=agent_stripe_account,
            client_id=merchant.id,
            idempotency_key=f"sub-{merchant.id}-{period_start}",
        )
    except SubscriptionChargeError as exc:
        raise HTTPException(status_code=402, detail=f"Subscription payment failed: {exc}")

    # Records the payment + a balanced commission row, advances billing, and
    # clears any dunning state (status -> active). Shared with the dunning sweep.
    await record_settled_payment(
        db,
        merchant=merchant,
        payer_user_id=str(current_user.id),
        charge=charge,
        cycle=cycle,
        period_start=period_start,
        period_end=period_end,
        agent_row=agent_row,
    )
    await db.commit()
    await db.refresh(merchant)
    return await _subscription_payload(db, merchant)


@router.get("/client/subscription/payments/{payment_id}/invoice")
async def get_subscription_invoice_pdf(
    payment_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Client: download the PRN-08 subscription invoice for one paid period (CL-09).

    The agent (white-label reseller) is the seller; the client merchant is the
    buyer. Always-Arabic A4 PDF (non-fiscal: no ZATCA QR/stamp). Owner-scoped —
    a client can only fetch invoices for their **own** subscription payments
    (SEC-02); an unknown/foreign payment id is a 404.
    """
    from fastapi.responses import Response

    from services.pdf_render import subscription_invoice_pdf_bytes

    merchant = await _client_for_current_user(db, str(current_user.id))
    payment = (
        await db.execute(
            select(Subscription_payments).where(
                Subscription_payments.id == payment_id,
                Subscription_payments.client_id == merchant.id,
            )
        )
    ).scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=404, detail="Subscription payment not found")

    agent_row = (
        await db.execute(select(Agents).where(Agents.id == merchant.agent_id))
    ).scalar_one_or_none()
    seller_name = (agent_row.company_name if agent_row else None) or "Platform"
    # Agents carry no VAT number today, so the seller VAT block is omitted per
    # PRN-08 ("VAT if agent VAT-registered"); future-proofed via getattr.
    seller_vat = (getattr(agent_row, "vat_number", "") or "") if agent_row else ""

    invoice_number = f"SUB-{merchant.id:04d}-{payment.id:06d}"
    issue_date = (
        payment.created_at.strftime("%Y-%m-%d")
        if payment.created_at
        else (payment.period_start or "")
    )
    try:
        pdf_bytes = subscription_invoice_pdf_bytes(
            seller_name=seller_name,
            buyer_name=merchant.business_name or "Client",
            invoice_number=invoice_number,
            issue_date=issue_date,
            period_start=payment.period_start or "",
            period_end=payment.period_end or "",
            billing_cycle=payment.billing_cycle or merchant.billing_cycle or "monthly",
            fee=payment.amount or 0,
            seller_vat=seller_vat,
            buyer_vat=merchant.vat_number or "",
            vat_amount=0.0,
            payment_status="paid",
            payment_method=payment.method or "manual",
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=501, detail=str(exc))

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{invoice_number}.pdf"'},
    )


# ---------- Client self-service profile (CL-02 first-login business type) ----------
# Valid POS modes. ``business_type`` discriminates retail vs restaurant and gates
# the restaurant vertical (RST-*, see routers/restaurant.py); it is set as a
# default by the agent at provisioning and the client confirms/changes it during
# the first-login setup flow (CL-02).
_VALID_BUSINESS_TYPES = ("retail", "restaurant", "both")


class ClientProfileResponse(BaseModel):
    client_id: int
    business_name: str
    business_type: str
    language_preference: str


class UpdateBusinessTypeRequest(BaseModel):
    business_type: str


@router.get("/client/profile", response_model=ClientProfileResponse)
async def get_client_profile(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Client: read own profile (business_type drives retail/restaurant POS mode, CL-02).

    Used by the first-login setup screen to pre-select the agent-provisioned
    business type before the client confirms it. Scoped to the caller's own
    ``Clients`` row (``_client_for_current_user`` 403s a non-client).
    """
    merchant = await _client_for_current_user(db, str(current_user.id))
    return ClientProfileResponse(
        client_id=merchant.id,
        business_name=merchant.business_name,
        business_type=(merchant.business_type or "retail"),
        language_preference=merchant.language_preference or "en",
    )


@router.post("/client/business-type", response_model=ClientProfileResponse)
async def set_client_business_type(
    data: UpdateBusinessTypeRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Client: set own business type during first-login setup (SRS CL-02).

    "Client picks language and business type during first-login setup." The agent
    seeds a default at provisioning; here the merchant confirms/changes it on their
    own account. The selection drives retail vs restaurant POS mode and gates the
    restaurant vertical (RST-*). Scoped to the caller's own ``Clients`` row via
    ``_client_for_current_user`` — a client can only ever change their **own**
    business type (SEC-02); a non-client (agent/master/no-client account) gets 403.
    """
    business_type = (data.business_type or "").strip().lower()
    if business_type not in _VALID_BUSINESS_TYPES:
        raise HTTPException(
            status_code=400,
            detail="business_type must be one of: retail, restaurant, both",
        )

    merchant = await _client_for_current_user(db, str(current_user.id))
    await db.execute(
        update(Clients).where(Clients.id == merchant.id).values(business_type=business_type)
    )
    await db.commit()
    await db.refresh(merchant)
    return ClientProfileResponse(
        client_id=merchant.id,
        business_name=merchant.business_name,
        business_type=(merchant.business_type or "retail"),
        language_preference=merchant.language_preference or "en",
    )


@router.put("/agent/clients/{client_id}/subscription", response_model=SubscriptionResponse)
async def update_client_subscription(
    client_id: int,
    data: UpdateSubscriptionRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Agent: set a client's subscription fee / billing cycle (CL-03)."""
    role_info = await get_user_role(db, str(current_user.id))
    if role_info["role"] != "agent":
        raise HTTPException(status_code=403, detail="Only agents can access this endpoint")

    result = await db.execute(
        select(Clients).where(
            Clients.id == client_id, Clients.agent_id == role_info["entity_id"]
        )
    )
    merchant = result.scalar_one_or_none()
    if not merchant:
        raise HTTPException(status_code=404, detail="Client not found")

    values: dict = {}
    if data.subscription_fee is not None:
        if data.subscription_fee < 0:
            raise HTTPException(status_code=400, detail="subscription_fee cannot be negative")
        values["subscription_fee"] = data.subscription_fee
    if data.billing_cycle is not None:
        if data.billing_cycle not in ("monthly", "yearly"):
            raise HTTPException(status_code=400, detail="billing_cycle must be monthly or yearly")
        values["billing_cycle"] = data.billing_cycle
    if values:
        await db.execute(update(Clients).where(Clients.id == client_id).values(**values))
        await db.commit()
        await db.refresh(merchant)
    return await _subscription_payload(db, merchant)


@router.post("/agent/clients/{client_id}/suspend-overdue", response_model=ToggleResponse)
async def suspend_overdue_client(
    client_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Agent: suspend a client whose subscription is past due (CL-05 non-payment).

    Marks ``subscription_status='suspended'`` and ``is_active=False`` so the
    merchant is blocked at authentication until they pay.
    """
    role_info = await get_user_role(db, str(current_user.id))
    if role_info["role"] != "agent":
        raise HTTPException(status_code=403, detail="Only agents can access this endpoint")

    result = await db.execute(
        select(Clients).where(
            Clients.id == client_id, Clients.agent_id == role_info["entity_id"]
        )
    )
    merchant = result.scalar_one_or_none()
    if not merchant:
        raise HTTPException(status_code=404, detail="Client not found")

    await db.execute(
        update(Clients)
        .where(Clients.id == client_id)
        .values(is_active=False, subscription_status="suspended")
    )
    await db.commit()
    return ToggleResponse(success=True, is_active=False)


class DunningRunResponse(BaseModel):
    processed: int
    recovered: int
    past_due: int
    dunning: int
    suspended: int


@router.post("/agent/billing/run-dunning", response_model=DunningRunResponse)
async def run_dunning_sweep(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Agent: run the dunning sweep across their own overdue merchants (CL-06).

    Retries the subscription charge for every merchant whose billing date has
    passed (or who is already past_due/dunning). A successful retry recovers the
    account (status -> active, billing advanced, payment recorded); a failed
    retry escalates active -> past_due -> dunning -> suspended. Owner-scoped: only
    the calling agent's own clients are touched (SEC-02). There is no always-on
    scheduler on the standalone deployment, so this is operator-triggered (the
    same pattern as the ZATCA reconcile sweep, F-020).
    """
    role_info = await get_user_role(db, str(current_user.id))
    if role_info["role"] != "agent":
        raise HTTPException(status_code=403, detail="Only agents can access this endpoint")

    from services.dunning import run_agent_dunning

    summary = await run_agent_dunning(
        db, role_info["entity_id"], actor_user_id=str(current_user.id)
    )
    return DunningRunResponse(**summary)


# ---------- Stripe billing webhook (CL-05 auto-suspend on non-payment) ----------
_FAILURE_EVENTS = {
    "invoice.payment_failed",
    "charge.failed",
    "payment_intent.payment_failed",
}
_RECOVERY_EVENTS = {
    "invoice.payment_succeeded",
    "payment_intent.succeeded",
}


@router.post("/billing/webhook")
async def stripe_billing_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Stripe webhook: auto-suspend a client on a failed subscription charge.

    Verifies the signature when ``STRIPE_WEBHOOK_SECRET`` is set (production); in
    dev/test (no secret) the JSON body is parsed directly. A failed payment event
    carrying ``metadata.client_id`` suspends that client (``is_active=False`` +
    ``subscription_status='suspended'``), which blocks them at authentication
    until they pay; a recovery event re-activates them.
    """
    from core.config import settings as _settings

    payload = await request.body()
    secret = getattr(_settings, "stripe_webhook_secret", None)
    if secret:
        import stripe

        sig = request.headers.get("stripe-signature", "")
        try:
            event = stripe.Webhook.construct_event(payload, sig, secret)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid webhook signature")
        event_type = event.get("type")
        data_object = event.get("data", {}).get("object", {})
    else:
        try:
            event = json.loads(payload or b"{}")
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid webhook payload")
        event_type = event.get("type")
        data_object = (event.get("data") or {}).get("object", {})

    metadata = data_object.get("metadata") or {}
    client_id = metadata.get("client_id")
    if not client_id:
        return {"received": True, "action": "ignored", "reason": "no client_id"}

    try:
        client_id_int = int(client_id)
    except (TypeError, ValueError):
        return {"received": True, "action": "ignored", "reason": "bad client_id"}

    if event_type in _FAILURE_EVENTS:
        await db.execute(
            update(Clients)
            .where(Clients.id == client_id_int)
            .values(is_active=False, subscription_status="suspended")
        )
        await db.commit()
        return {"received": True, "action": "suspended", "client_id": client_id_int}

    if event_type in _RECOVERY_EVENTS:
        await db.execute(
            update(Clients)
            .where(Clients.id == client_id_int)
            .values(is_active=True, subscription_status="active")
        )
        await db.commit()
        return {"received": True, "action": "reactivated", "client_id": client_id_int}

    return {"received": True, "action": "ignored", "event": event_type}


# ---------- Public Endpoints (no auth required) ----------
class AgentPublicProfileResponse(BaseModel):
    company_name: str
    logo_url: Optional[str] = None
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    tagline: Optional[str] = None
    features: List[str] = []
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None


@router.get("/agent/{agent_id}/public", response_model=AgentPublicProfileResponse)
async def get_agent_public_profile(
    agent_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Public: Get agent's public profile for their landing page (no auth required)"""
    result = await db.execute(select(Agents).where(Agents.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent or not (agent.is_active if agent.is_active is not None else True):
        raise HTTPException(status_code=404, detail="Agent not found or inactive")

    # Get agent features
    features_result = await db.execute(
        select(Agent_features).where(
            Agent_features.agent_id == agent_id,
            Agent_features.is_enabled == True,
        )
    )
    features = features_result.scalars().all()
    feature_names = [f.feature_name for f in features] if features else [
        "Point of Sale Terminal",
        "ZATCA Compliant Invoicing",
        "Multi-language Support",
        "Sales Analytics",
    ]

    return AgentPublicProfileResponse(
        company_name=agent.company_name,
        logo_url=agent.logo_url,
        primary_color=agent.primary_color or "#3B82F6",
        secondary_color=agent.secondary_color or "#1E40AF",
        tagline=getattr(agent, 'tagline', None),
        features=feature_names,
        contact_email=agent.email,
        contact_phone=agent.phone,
    )


@router.get("/client/dashboard", response_model=DashboardStatsResponse)
async def get_client_dashboard(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Client: Get dashboard statistics"""
    role_info = await get_user_role(db, str(current_user.id))
    if role_info["role"] != "client":
        raise HTTPException(status_code=403, detail="Only clients can access this endpoint")

    client_id = role_info["entity_id"]

    # Total sales
    total_result = await db.execute(
        select(func.coalesce(func.sum(Transactions.total_amount), 0))
        .where(Transactions.client_id == client_id)
    )
    total_sales = float(total_result.scalar() or 0)

    # Total transactions
    count_result = await db.execute(
        select(func.count(Transactions.id)).where(Transactions.client_id == client_id)
    )
    total_transactions = count_result.scalar() or 0

    # Today's transactions
    today = datetime.now(timezone.utc).date()
    today_count_result = await db.execute(
        select(func.count(Transactions.id))
        .where(Transactions.client_id == client_id)
        .where(func.date(Transactions.created_at) == today)
    )
    today_transactions = today_count_result.scalar() or 0

    # Today's sales
    today_sales_result = await db.execute(
        select(func.coalesce(func.sum(Transactions.total_amount), 0))
        .where(Transactions.client_id == client_id)
        .where(func.date(Transactions.created_at) == today)
    )
    today_sales = float(today_sales_result.scalar() or 0)

    # Products count
    products_result = await db.execute(
        select(func.count(Products.id)).where(Products.client_id == client_id)
    )
    products_count = products_result.scalar() or 0

    return DashboardStatsResponse(
        total_sales=total_sales,
        total_transactions=total_transactions,
        today_transactions=today_transactions,
        today_sales=today_sales,
        products_count=products_count,
    )