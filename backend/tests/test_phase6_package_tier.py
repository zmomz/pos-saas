"""MA-07 (F-024): a package's feature-entitlement tier actually gates capabilities.

Before this finding, ``packages`` carried slot counts and prices only — the
"which feature tier a package unlocks" half of MA-07 was absent, so a package
never influenced what a provisioned merchant could do. This pins the real
behaviour end-to-end through the live endpoints:

  * a master defines a package with a ``features`` tier (the enabled keys);
  * an agent provisioned from that package inherits the tier in ``agent_features``;
  * a client the agent provisions (with no explicit feature list) inherits the
    tier in ``client_features`` — keys outside the tier are explicitly disabled,
    so ``require_feature`` actually blocks them (features are enabled-by-default,
    so only an ``is_enabled=False`` row gates a capability);
  * a package with no tier leaves every feature enabled (backward compatible);
  * an unknown feature key is rejected (400), never stored.
"""
import pytest
from sqlalchemy import select

from conftest import auth_headers, make_master_account, unique_email
from core.database import db_manager
from dependencies.features import FEATURE_KEYS, is_feature_enabled
from models.agent_features import Agent_features
from models.client_features import Client_features


async def _create_package(client, master_token, features):
    return await client.post(
        "/api/v1/packages/create",
        json={
            "name": "Tier Pack",
            "client_slots": 5,
            "wholesale_price": 100.0,
            "suggested_retail_price": 150.0,
            "features": features,
        },
        headers=auth_headers(master_token),
    )


async def _create_agent_from_package(client, master_token, package_id):
    email = unique_email()
    resp = await client.post(
        "/api/v1/tenant/master/agents",
        json={"company_name": "Tier Agent", "email": email, "package_id": package_id},
        headers=auth_headers(master_token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return email, body["temp_password"], body["id"]


async def _login(client, email, password):
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


async def _provision_client(client, agent_token, features=None):
    payload = {"business_name": "Merchant", "email": unique_email()}
    if features is not None:
        payload["features"] = features
    resp = await client.post(
        "/api/v1/tenant/agent/clients", json=payload, headers=auth_headers(agent_token)
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_package_tier_seeds_client_features_to_match_tier(client):
    """Provisioning a client via a tiered package seeds client_features = the tier."""
    _mu, master_token = await make_master_account(client)
    tier = ["email_receipts", "loyalty"]

    pkg = await _create_package(client, master_token, tier)
    assert pkg.status_code == 200, pkg.text
    assert sorted(pkg.json()["features"]) == sorted(tier)  # round-trips through the API
    package_id = pkg.json()["id"]

    email, temp_pw, _agent_id = await _create_agent_from_package(
        client, master_token, package_id
    )
    agent_token = await _login(client, email, temp_pw)

    created = await _provision_client(client, agent_token)
    client_id = created["id"]

    async with db_manager.async_session_maker() as db:
        rows = (
            await db.execute(
                select(Client_features.feature_name, Client_features.is_enabled).where(
                    Client_features.client_id == client_id
                )
            )
        ).all()
        flags = {name: bool(enabled) for name, enabled in rows}
        # every canonical key has an explicit row reflecting the tier
        assert set(flags) == set(FEATURE_KEYS)
        for key in FEATURE_KEYS:
            assert flags[key] == (key in tier), key
        # and the gate honours it
        for key in FEATURE_KEYS:
            assert (await is_feature_enabled(db, client_id, key)) == (key in tier), key


@pytest.mark.asyncio
async def test_package_without_tier_leaves_all_client_features_enabled(client):
    """A package with no tier provisions a client with everything enabled (no rows)."""
    _mu, master_token = await make_master_account(client)

    pkg = await _create_package(client, master_token, None)
    assert pkg.status_code == 200, pkg.text
    assert pkg.json()["features"] is None
    package_id = pkg.json()["id"]

    email, temp_pw, _agent_id = await _create_agent_from_package(
        client, master_token, package_id
    )
    agent_token = await _login(client, email, temp_pw)
    created = await _provision_client(client, agent_token)
    client_id = created["id"]

    async with db_manager.async_session_maker() as db:
        rows = (
            await db.execute(
                select(Client_features).where(Client_features.client_id == client_id)
            )
        ).scalars().all()
        assert rows == []  # no disabling rows
        for key in FEATURE_KEYS:
            assert (await is_feature_enabled(db, client_id, key)) is True, key


@pytest.mark.asyncio
async def test_agent_features_seeded_from_package_tier(client):
    """An agent provisioned from a tiered package inherits the tier in agent_features."""
    _mu, master_token = await make_master_account(client)
    tier = ["inventory", "discounts", "loyalty"]

    pkg = await _create_package(client, master_token, tier)
    package_id = pkg.json()["id"]
    _email, _pw, agent_id = await _create_agent_from_package(
        client, master_token, package_id
    )

    async with db_manager.async_session_maker() as db:
        rows = (
            await db.execute(
                select(
                    Agent_features.feature_name, Agent_features.is_enabled_default
                ).where(Agent_features.agent_id == agent_id)
            )
        ).all()
        flags = {name: bool(enabled) for name, enabled in rows}
        assert set(flags) == set(FEATURE_KEYS)
        for key in FEATURE_KEYS:
            assert flags[key] == (key in tier), key


@pytest.mark.asyncio
async def test_package_rejects_unknown_feature_key(client):
    """A feature key outside FEATURE_KEYS is rejected (400), never stored."""
    _mu, master_token = await make_master_account(client)
    resp = await _create_package(client, master_token, ["loyalty", "teleport"])
    assert resp.status_code == 400, resp.text
    assert "teleport" in resp.text
