"""Phase 5 — Admin & white-label completeness (subscription, feature gating, logo).

Covers the backend gaps closed in Phase 5:
* CL-03/CL-04 subscription: agent sets fee/cycle, client reads status + history,
  paying records a payment and advances the next billing date;
* CL-05 non-payment: agent suspends an overdue client (blocked at auth);
* AG-03 feature gating: disabling 'loyalty' for a client 403s the loyalty route,
  while another client is unaffected (default-enabled);
* AG-01 logo upload: valid image stored + URL persisted; non-image / oversized
  rejected.
"""
import io

from sqlalchemy import select

from conftest import (
    auth_headers,
    make_agent_account,
    make_client_under_agent,
)
from core.database import db_manager
from models.clients import Clients


# ---------------------------------------------------------------------------
# CL-03 / CL-04: subscription lifecycle
# ---------------------------------------------------------------------------
async def test_agent_sets_fee_then_client_pays_and_advances(client):
    _agent, agent_token, agent_id = await make_agent_account(client)
    _cu, client_token, client_id = await make_client_under_agent(client, agent_id)

    # CL-03: agent sets the subscription fee + cycle.
    resp = await client.put(
        f"/api/v1/tenant/agent/clients/{client_id}/subscription",
        json={"subscription_fee": 99.0, "billing_cycle": "monthly"},
        headers=auth_headers(agent_token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["subscription_fee"] == 99.0

    # CL-04: client sees status + (empty) history before paying.
    status = (
        await client.get("/api/v1/tenant/client/subscription", headers=auth_headers(client_token))
    ).json()
    assert status["subscription_fee"] == 99.0
    assert status["payments"] == []

    # Paying records a payment and advances next billing.
    paid = (
        await client.post(
            "/api/v1/tenant/client/subscription/pay", headers=auth_headers(client_token)
        )
    ).json()
    assert paid["subscription_status"] == "active"
    assert len(paid["payments"]) == 1
    assert paid["payments"][0]["amount"] == 99.0
    assert paid["next_billing_date"]  # advanced one cycle


async def test_pay_without_fee_is_rejected(client):
    _agent, _agent_token, agent_id = await make_agent_account(client)
    _cu, client_token, _client_id = await make_client_under_agent(client, agent_id)

    resp = await client.post(
        "/api/v1/tenant/client/subscription/pay", headers=auth_headers(client_token)
    )
    assert resp.status_code == 400
    assert "fee" in resp.json()["detail"].lower()


async def test_agent_suspends_overdue_client(client):
    _agent, agent_token, agent_id = await make_agent_account(client)
    _cu, client_token, client_id = await make_client_under_agent(client, agent_id)

    resp = await client.post(
        f"/api/v1/tenant/agent/clients/{client_id}/suspend-overdue",
        headers=auth_headers(agent_token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_active"] is False

    async with db_manager.async_session_maker() as db:
        merchant = (
            await db.execute(select(Clients).where(Clients.id == client_id))
        ).scalar_one()
        assert merchant.is_active is False
        assert merchant.subscription_status == "suspended"


# ---------------------------------------------------------------------------
# AG-03: per-client feature gating
# ---------------------------------------------------------------------------
async def test_disabled_feature_gates_route_403(client):
    _agent, agent_token, agent_id = await make_agent_account(client)
    _cu, client_token, client_id = await make_client_under_agent(client, agent_id)

    # Loyalty is enabled by default — the route is reachable.
    ok = await client.post(
        "/api/v1/production/loyalty/earn",
        json={"customer_id": 1, "transaction_amount": 100.0, "points_rate": 1.0},
        headers=auth_headers(client_token),
    )
    assert ok.status_code == 200, ok.text

    # Agent disables loyalty for this client.
    toggle = await client.post(
        f"/api/v1/tenant/agent/clients/{client_id}/features",
        json={"feature_name": "loyalty", "is_enabled": False},
        headers=auth_headers(agent_token),
    )
    assert toggle.status_code == 200, toggle.text

    # Now the gated route 403s for that client.
    denied = await client.post(
        "/api/v1/production/loyalty/earn",
        json={"customer_id": 1, "transaction_amount": 100.0, "points_rate": 1.0},
        headers=auth_headers(client_token),
    )
    assert denied.status_code == 403
    assert "loyalty" in denied.json()["detail"].lower()


async def test_feature_disable_is_per_client(client):
    _agent, agent_token, agent_id = await make_agent_account(client)
    _a, token_a, id_a = await make_client_under_agent(client, agent_id)
    _b, token_b, _id_b = await make_client_under_agent(client, agent_id)

    await client.post(
        f"/api/v1/tenant/agent/clients/{id_a}/features",
        json={"feature_name": "loyalty", "is_enabled": False},
        headers=auth_headers(agent_token),
    )

    # Sibling client B is unaffected (default-enabled).
    resp_b = await client.post(
        "/api/v1/production/loyalty/earn",
        json={"customer_id": 1, "transaction_amount": 50.0, "points_rate": 1.0},
        headers=auth_headers(token_b),
    )
    assert resp_b.status_code == 200, resp_b.text


# ---------------------------------------------------------------------------
# AG-01: logo upload
# ---------------------------------------------------------------------------
# Smallest valid PNG (1x1).
_PNG_1x1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000100"
    "05fe02fea7e1d40000000049454e44ae426082"
)


async def test_logo_upload_stores_and_persists_url(client):
    _agent, agent_token, agent_id = await make_agent_account(client)

    resp = await client.post(
        "/api/v1/tenant/agent/logo",
        files={"file": ("logo.png", io.BytesIO(_PNG_1x1), "image/png")},
        headers=auth_headers(agent_token),
    )
    assert resp.status_code == 200, resp.text
    logo_url = resp.json()["logo_url"]
    assert logo_url.startswith("/uploads/logos/")

    # The agent's branding now reports the uploaded logo.
    branding = (
        await client.get("/api/v1/tenant/agent/branding", headers=auth_headers(agent_token))
    ).json()
    assert branding["logo_url"] == logo_url


async def test_logo_upload_rejects_non_image(client):
    _agent, agent_token, _agent_id = await make_agent_account(client)
    resp = await client.post(
        "/api/v1/tenant/agent/logo",
        files={"file": ("evil.txt", io.BytesIO(b"not an image"), "text/plain")},
        headers=auth_headers(agent_token),
    )
    assert resp.status_code == 400


async def test_logo_upload_rejects_oversized(client):
    _agent, agent_token, _agent_id = await make_agent_account(client)
    big = io.BytesIO(b"\x89PNG" + b"0" * (2 * 1024 * 1024 + 10))
    resp = await client.post(
        "/api/v1/tenant/agent/logo",
        files={"file": ("big.png", big, "image/png")},
        headers=auth_headers(agent_token),
    )
    assert resp.status_code == 413
