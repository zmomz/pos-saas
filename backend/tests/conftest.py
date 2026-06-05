"""Shared pytest fixtures for the backend test suite.

Environment variables are set BEFORE importing the application so the settings
singleton and module-level app construction pick up a throwaway SQLite database
and a deterministic JWT secret. The app's lazy DB initialization (``get_db`` ->
``ensure_initialized``) creates the schema on first use, so we don't run the
ASGI lifespan here.
"""
import os
import uuid

# ---- Must run before importing the app / settings ----
_TEST_DB = os.path.join(os.path.dirname(__file__), "_test_app.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-pytest-only"
os.environ["ENVIRONMENT"] = "dev"
os.environ["SKIP_INIT_ADMIN"] = "1"
os.environ["ALLOW_REGISTRATION"] = "true"
# Ensure no Stripe key leaks in from the developer environment.
os.environ.pop("STRIPE_SECRET_KEY", None)

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from core.database import db_manager  # noqa: E402
from main import app  # noqa: E402
from models.agents import Agents  # noqa: E402
from models.clients import Clients  # noqa: E402
from models.products import Products  # noqa: E402


def unique_email() -> str:
    return f"user_{uuid.uuid4().hex[:12]}@example.com"


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _init_db():
    """Initialize the database schema once for the whole test session."""
    # Start from a clean file so counts/assertions are deterministic.
    if os.path.exists(_TEST_DB):
        try:
            os.remove(_TEST_DB)
        except OSError:
            pass
    await db_manager.ensure_initialized()
    yield
    await db_manager.close_db()


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def register_user(client: AsyncClient, email: str | None = None, password: str = "Password123"):
    """Register a fresh user and return (user_dict, token, refresh_token)."""
    email = email or unique_email()
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "name": "Test User"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["user"], body["token"], body.get("refresh_token", "")


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def make_client_account(client: AsyncClient, is_active: bool = True, business_type: str = "retail"):
    """Register a user and attach a tenancy *client* row (+ an owning agent).

    ``business_type`` (retail / restaurant / both, CL-02) controls whether the
    client can reach the restaurant vertical (RST-*).

    Returns (user_dict, token, client_id).
    """
    email = unique_email()
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123", "name": "Client User"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    user, token = body["user"], body["token"]

    async with db_manager.async_session_maker() as db:
        agent = Agents(
            user_id=str(uuid.uuid4()),
            company_name="Test Agent",
            email=unique_email(),
            package_type=1,
            used_slots=0,
            is_active=True,
        )
        db.add(agent)
        await db.commit()
        await db.refresh(agent)

        merchant = Clients(
            user_id=user["id"],
            agent_id=agent.id,
            business_name="Test Shop",
            email=email,
            is_active=is_active,
            business_type=business_type,
            invoice_counter=0,
        )
        db.add(merchant)
        await db.commit()
        await db.refresh(merchant)
        client_id = merchant.id

    return user, token, client_id


async def make_master_account(client: AsyncClient):
    """Register a user and promote them to platform master (User.role='admin').

    Role resolution (``get_user_role``) treats an admin account with no agent/client
    row as master. Returns (user_dict, token).
    """
    from sqlalchemy import update

    from models.auth import User

    user, token, _ = await register_user(client)
    async with db_manager.async_session_maker() as db:
        await db.execute(update(User).where(User.id == user["id"]).values(role="admin"))
        await db.commit()
    return user, token


async def make_agent_account(client: AsyncClient, package_type: int = 5):
    """Register a user and attach an owning ``Agents`` row so they resolve as agent.

    Returns (user_dict, token, agent_id).
    """
    user, token, _ = await register_user(client)
    async with db_manager.async_session_maker() as db:
        agent = Agents(
            user_id=user["id"],
            company_name="Agent Co",
            email=unique_email(),
            package_type=package_type,
            used_slots=0,
            is_active=True,
        )
        db.add(agent)
        await db.commit()
        await db.refresh(agent)
        return user, token, agent.id


async def make_client_under_agent(client: AsyncClient, agent_id: int, is_active: bool = True):
    """Register a real login user and attach a ``Clients`` row under ``agent_id``.

    Returns (user_dict, token, client_id).
    """
    email = unique_email()
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123", "name": "Merchant"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    user, token = body["user"], body["token"]
    async with db_manager.async_session_maker() as db:
        merchant = Clients(
            user_id=user["id"],
            agent_id=agent_id,
            business_name="Shop",
            email=email,
            is_active=is_active,
            invoice_counter=0,
        )
        db.add(merchant)
        await db.commit()
        await db.refresh(merchant)
        return user, token, merchant.id


async def add_product(
    client_id: int,
    user_id: str,
    name: str = "Widget",
    quantity: int = 5,
    price: float = 10.0,
    cost_price: float | None = None,
):
    async with db_manager.async_session_maker() as db:
        product = Products(
            user_id=user_id,
            client_id=client_id,
            name=name,
            price=price,
            quantity=quantity,
            cost_price=cost_price,
            is_active=True,
        )
        db.add(product)
        await db.commit()
        await db.refresh(product)
        return product.id


async def get_product_quantity(product_id: int) -> int:
    from sqlalchemy import select

    async with db_manager.async_session_maker() as db:
        result = await db.execute(select(Products.quantity).where(Products.id == product_id))
        return result.scalar_one()
