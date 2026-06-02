import json
import logging
import hashlib
import base64
import secrets
import struct
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.security import hash_password
from dependencies.auth import get_current_user
from schemas.auth import UserResponse
from models.auth import User
from models.agents import Agents
from models.clients import Clients
from models.packages import Packages
from models.products import Products
from models.transactions import Transactions
from models.agent_features import Agent_features
from models.client_features import Client_features
from services.system_settings import (
    GLOBAL_TAX_RATE_KEY,
    get_global_tax_rate,
    set_setting,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/tenant", tags=["tenant"])


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

class CreateClientRequest(BaseModel):
    business_name: str
    email: str
    phone: Optional[str] = None
    subscription_fee: Optional[float] = 0
    language_preference: Optional[str] = "en"
    features: Optional[List[str]] = None

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

    # Resolve the agent's client-slot allowance.
    slots = data.slots or 0
    if data.package_id is not None:
        pkg_result = await db.execute(select(Packages).where(Packages.id == data.package_id))
        package = pkg_result.scalar_one_or_none()
        if not package:
            raise HTTPException(status_code=404, detail="Package not found")
        slots = package.client_slots
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
        used_slots=0,
        is_active=True,
    )
    db.add(new_agent)
    await db.commit()
    await db.refresh(new_agent)

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
            zatca_enabled=client.zatca_enabled if client.zatca_enabled is not None else False,
            language_preference=client.language_preference or "en",
            created_at=client.created_at,
        ))

    return AgentClientsResponse(items=items, total=total, remaining_slots=remaining_slots)


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
    )


@router.post("/agent/clients", response_model=ClientListItem)
async def create_client_for_agent(
    data: CreateClientRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Agent: Create a new client (deducts slot)"""
    role_info = await get_user_role(db, str(current_user.id))
    if role_info["role"] != "agent":
        raise HTTPException(status_code=403, detail="Only agents can access this endpoint")

    agent_id = role_info["entity_id"]

    # Check available slots
    agent_result = await db.execute(select(Agents).where(Agents.id == agent_id))
    agent = agent_result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    used = agent.used_slots or 0
    if used >= (agent.package_type or 0):
        raise HTTPException(status_code=400, detail="No available client slots. Please upgrade your package.")

    # Create client
    new_client = Clients(
        user_id=str(current_user.id),
        agent_id=agent_id,
        business_name=data.business_name,
        email=data.email,
        phone=data.phone,
        subscription_fee=data.subscription_fee or 0,
        is_active=True,
        language_preference=data.language_preference or "en",
        zatca_enabled=False,
        invoice_counter=0,
    )
    db.add(new_client)

    # Deduct slot
    await db.execute(
        update(Agents).where(Agents.id == agent_id).values(used_slots=used + 1)
    )
    await db.commit()
    await db.refresh(new_client)

    # Create default features for client
    if data.features:
        for feature in data.features:
            cf = Client_features(
                user_id=str(current_user.id),
                client_id=new_client.id,
                feature_name=feature,
                is_enabled=True,
            )
            db.add(cf)
        await db.commit()

    return ClientListItem(
        id=new_client.id,
        business_name=new_client.business_name,
        email=new_client.email,
        phone=new_client.phone,
        subscription_fee=new_client.subscription_fee,
        is_active=True,
        zatca_enabled=False,
        language_preference=new_client.language_preference or "en",
        created_at=new_client.created_at,
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
    )


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