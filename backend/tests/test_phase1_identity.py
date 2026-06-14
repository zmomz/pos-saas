"""Phase 1 — Identity & tenancy foundation regression tests.

Covers the critical defects closed in Phase 1:
  C-1  provisioned clients get a real, loggable account (own user_id, temp pw)
  C-2  suspension targets the merchant, not the agent / siblings
  MA-02 slot deduction is atomic — a full package cannot be oversold
  H14/H15 the orphaned clients/client_features CRUD scaffolds — incl. the
       cross-tenant `/clients/all` read — are deleted, not mounted
  C-6  the generic transactions triad cannot create/mutate fiscal records
  first-login force-reset clears must_change_password on password change
"""
import uuid

from sqlalchemy import select

from conftest import (
    add_product,
    auth_headers,
    make_agent_account,
    register_user,
    unique_email,
)
from core.database import db_manager
from models.agents import Agents
from models.clients import Clients


async def _provision_client(client, agent_token, email=None, **extra):
    """Create a client through the agent endpoint; return the response body."""
    email = email or unique_email()
    resp = await client.post(
        "/api/v1/tenant/agent/clients",
        json={"business_name": "Merchant", "email": email, **extra},
        headers=auth_headers(agent_token),
    )
    return resp, email


# ---------------------------------------------------------------- C-1
async def test_provisioned_client_gets_loggable_account(client):
    _agent_user, agent_token, agent_id = await make_agent_account(client, package_type=5)
    resp, email = await _provision_client(client, agent_token)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # A one-time temp password is returned and flagged for reset.
    assert body["temp_password"]
    assert body["must_change_password"] is True

    # The temp password actually works as a login.
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": body["temp_password"]}
    )
    assert login.status_code == 200, login.text
    assert login.json()["user"]["must_change_password"] is True

    # The Clients row points at the merchant's NEW user, not the agent's account.
    async with db_manager.async_session_maker() as db:
        merchant = (
            await db.execute(select(Clients).where(Clients.id == body["id"]))
        ).scalar_one()
        agent = (
            await db.execute(select(Agents).where(Agents.id == agent_id))
        ).scalar_one()
        assert merchant.user_id != agent.user_id
        assert merchant.user_id == login.json()["user"]["id"]


async def test_duplicate_client_email_rejected(client):
    _u, agent_token, _aid = await make_agent_account(client, package_type=5)
    email = unique_email()
    first, _ = await _provision_client(client, agent_token, email=email)
    assert first.status_code == 200, first.text
    dup, _ = await _provision_client(client, agent_token, email=email)
    assert dup.status_code == 409


# ---------------------------------------------------------------- C-2
async def test_suspension_targets_merchant_not_agent_or_siblings(client):
    _agent_user, agent_token, _aid = await make_agent_account(client, package_type=5)
    a_resp, a_email = await _provision_client(client, agent_token)
    b_resp, b_email = await _provision_client(client, agent_token)
    a_body, b_body = a_resp.json(), b_resp.json()

    a_login = await client.post(
        "/api/v1/auth/login", json={"email": a_email, "password": a_body["temp_password"]}
    )
    b_login = await client.post(
        "/api/v1/auth/login", json={"email": b_email, "password": b_body["temp_password"]}
    )
    a_token = a_login.json()["token"]
    b_token = b_login.json()["token"]

    # Both clients and the agent can authenticate before suspension.
    assert (await client.get("/api/v1/auth/me", headers=auth_headers(a_token))).status_code == 200

    # Agent suspends client A.
    toggle = await client.post(
        f"/api/v1/tenant/agent/clients/{a_body['id']}/toggle",
        headers=auth_headers(agent_token),
    )
    assert toggle.status_code == 200 and toggle.json()["is_active"] is False

    # Only client A is locked out; sibling B and the agent are unaffected.
    assert (await client.get("/api/v1/auth/me", headers=auth_headers(a_token))).status_code == 403
    assert (await client.get("/api/v1/auth/me", headers=auth_headers(b_token))).status_code == 200
    assert (await client.get("/api/v1/auth/me", headers=auth_headers(agent_token))).status_code == 200


# ---------------------------------------------------------------- MA-02
async def test_slot_deduction_cannot_oversell(client):
    _u, agent_token, _aid = await make_agent_account(client, package_type=1)
    first, _ = await _provision_client(client, agent_token)
    assert first.status_code == 200, first.text
    second, _ = await _provision_client(client, agent_token)
    assert second.status_code == 409, second.text


# ---------------------------------------------------------------- H14/H15
async def test_no_clients_entity_crud_route_is_mounted(client):
    """H14/H15: the orphaned /api/v1/entities/clients and /client_features CRUD
    scaffolds scoped every op on user_id == current_user.id — a merchant could
    only ever read/mutate grants about its OWN login, never another tenant — and
    additionally exposed an admin /clients/all cross-tenant read (H15). No
    frontend caller; the live per-client toggle is the master/agent-gated path in
    tenant.py + features.py (AgentDashboard). Neither triad — including /all —
    may be mounted."""
    from main import app

    mounted = {getattr(r, "path", "") for r in app.routes}
    offenders = {
        p
        for p in mounted
        if p.startswith("/api/v1/entities/clients")
        or p.startswith("/api/v1/entities/client_features")
    }
    assert not offenders, f"orphaned clients CRUD route(s) still mounted: {sorted(offenders)}"


# ---------------------------------------------------------------- H1
async def test_no_packages_entity_crud_route_is_mounted(client):
    """H1: the orphaned /api/v1/entities/packages CRUD scaffold — full
    create/update/delete with no auth on the write verbs — must not be mounted.
    The only package surface is the master-gated path under /api/v1/packages."""
    from main import app

    mounted = {getattr(r, "path", "") for r in app.routes}
    offenders = {p for p in mounted if p.startswith("/api/v1/entities/packages")}
    assert not offenders, f"orphaned packages CRUD route(s) still mounted: {sorted(offenders)}"


async def test_no_agents_entity_crud_route_is_mounted(client):
    """H2: the orphaned /api/v1/entities/agents and /agent_features CRUD
    scaffolds let any authenticated user create/update/HARD-DELETE branding/
    feature-flag rows keyed on their own user_id. The real branding/provisioning
    surface is /api/v1/tenant + features.py; these triads must not be mounted."""
    from main import app

    mounted = {getattr(r, "path", "") for r in app.routes}
    offenders = {
        p
        for p in mounted
        if p.startswith("/api/v1/entities/agents")
        or p.startswith("/api/v1/entities/agent_features")
    }
    assert not offenders, f"orphaned agents CRUD route(s) still mounted: {sorted(offenders)}"


async def test_no_permissions_entity_crud_route_is_mounted(client):
    """H13: the generic /api/v1/entities/permissions CRUD scaffold scoped every
    op on Permissions.user_id == current_user.id — a self-ownership model where a
    user could only ever read/edit grants about themselves, with no frontend
    caller. RBAC is enforced through dependencies/permissions.py; this triad must
    not be mounted."""
    from main import app

    mounted = {getattr(r, "path", "") for r in app.routes}
    offenders = {p for p in mounted if p.startswith("/api/v1/entities/permissions")}
    assert not offenders, f"orphaned permissions CRUD route(s) still mounted: {sorted(offenders)}"


# ---------------------------------------------------------------- C-6
async def test_transactions_triad_is_read_only(client):
    _user, token, _ = await register_user(client)
    headers = auth_headers(token)
    payload = {
        "client_id": 1,
        "invoice_number": "FAKE-1",
        "total_amount": 100.0,
        "payment_method": "cash",
    }
    create = await client.post("/api/v1/entities/transactions", json=payload, headers=headers)
    assert create.status_code == 403, create.text
    delete = await client.delete("/api/v1/entities/transactions/1", headers=headers)
    assert delete.status_code == 403


# ---------------------------------------------------------------- isolation
async def test_client_cannot_read_other_clients_product(client):
    _u, agent_token, _aid = await make_agent_account(client, package_type=5)
    a_resp, a_email = await _provision_client(client, agent_token)
    b_resp, b_email = await _provision_client(client, agent_token)
    a_body, b_body = a_resp.json(), b_resp.json()

    a_login = await client.post(
        "/api/v1/auth/login", json={"email": a_email, "password": a_body["temp_password"]}
    )
    b_login = await client.post(
        "/api/v1/auth/login", json={"email": b_email, "password": b_body["temp_password"]}
    )
    a_user_id = a_login.json()["user"]["id"]
    b_token = b_login.json()["token"]

    product_id = await add_product(a_body["id"], a_user_id, name="A-Widget")

    # Owner reads it; the sibling tenant gets a 404 (owner-scoped).
    own = await client.get(
        f"/api/v1/entities/products/{product_id}",
        headers=auth_headers(a_login.json()["token"]),
    )
    assert own.status_code == 200, own.text
    cross = await client.get(
        f"/api/v1/entities/products/{product_id}", headers=auth_headers(b_token)
    )
    assert cross.status_code == 404


# ---------------------------------------------------------------- first-login reset
async def test_first_login_password_change_clears_flag(client):
    _u, agent_token, _aid = await make_agent_account(client, package_type=5)
    resp, email = await _provision_client(client, agent_token)
    body = resp.json()

    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": body["temp_password"]}
    )
    token = login.json()["token"]

    changed = await client.post(
        "/api/v1/users/change-password",
        json={"current_password": body["temp_password"], "new_password": "BrandNew123"},
        headers=auth_headers(token),
    )
    assert changed.status_code == 200, changed.text

    # A fresh login no longer demands a reset, and the new password works.
    relog = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "BrandNew123"}
    )
    assert relog.status_code == 200, relog.text
    assert relog.json()["user"]["must_change_password"] is False
