"""M10 / issue #219 — tenant-scoped read cache.

Covers the two halves of the issue:

1. the cache primitive itself (`core/cache.py`) — get/set, single-flight load,
   exact-key + prefix invalidation, and the no-Redis fallback used in CI; and
2. that the four hot reads (tax / features / brand / dashboard aggregates) are
   actually served from cache **and** invalidated on the matching write — proven
   by writing straight to the DB behind the cache's back: the stale value persists
   until the write path's invalidation runs.
"""
import uuid

import pytest

from core.cache import (
    brand_agent_key,
    brand_domain_key,
    cache,
    dashboard_key,
    feature_key,
    features_prefix,
    invalidate_features,
    invalidate_tax,
    tax_global_key,
)
from core.database import db_manager
from dependencies.features import is_feature_enabled
from models.agents import Agents
from models.client_features import Client_features
from services.products import ProductsService
from services.system_settings import (
    GLOBAL_TAX_RATE_KEY,
    get_global_tax_rate,
    set_setting,
)

from tests.conftest import (
    auth_headers,
    make_agent_account,
    make_client_account,
)

pytestmark = pytest.mark.asyncio


# ---------------- The cache primitive ----------------

async def test_set_get_roundtrip_and_delete():
    await cache.set_json("unit:k", {"a": 1}, ttl=60)
    assert await cache.get_json("unit:k") == {"a": 1}
    await cache.delete("unit:k")
    assert await cache.get_json("unit:k") is None


async def test_get_or_load_loads_once_then_serves_from_cache():
    calls = {"n": 0}

    async def loader():
        calls["n"] += 1
        return {"v": calls["n"]}

    first = await cache.get_or_load("unit:once", 60, loader)
    second = await cache.get_or_load("unit:once", 60, loader)
    assert first == {"v": 1}
    assert second == {"v": 1}  # served from cache, loader not re-run
    assert calls["n"] == 1


async def test_get_or_load_does_not_cache_none():
    async def loader():
        return None

    assert await cache.get_or_load("unit:none", 60, loader) is None
    # A None result is a miss, so nothing was stored.
    assert await cache.get_json("unit:none") is None


async def test_invalidate_prefix_only_clears_matching_keys():
    await cache.set_json("features:1:loyalty", True, 60)
    await cache.set_json("features:1:inventory", False, 60)
    await cache.set_json("features:2:loyalty", True, 60)

    await cache.invalidate_prefix(features_prefix(1))

    assert await cache.get_json("features:1:loyalty") is None
    assert await cache.get_json("features:1:inventory") is None
    # A different tenant's keys are untouched — invalidation is tenant-scoped.
    assert await cache.get_json("features:2:loyalty") is True


async def test_backend_is_memory_without_redis():
    # The test env sets no REDIS_URL, so the cache must run in-process.
    assert cache.backend_name == "memory"


async def test_key_builders_are_tenant_scoped():
    assert feature_key(7, "loyalty").startswith(features_prefix(7))
    assert brand_agent_key(7) != brand_agent_key(8)
    assert brand_domain_key("Shop.Example.COM") == brand_domain_key("shop.example.com")
    assert dashboard_key(7) == "dashboard:7"
    assert tax_global_key() == "tax:global_rate"


# ---------------- Tax rate: cached + invalidated on write ----------------

async def test_global_tax_rate_cached_until_invalidated():
    async with db_manager.async_session_maker() as db:
        # First read caches the "no global rate configured" answer.
        assert await get_global_tax_rate(db) is None

        # Write a rate straight to the DB, bypassing the router's invalidation.
        await set_setting(db, GLOBAL_TAX_RATE_KEY, "20")
        await db.commit()

        # The cache still serves the pre-write answer — proof the read is cached.
        assert await get_global_tax_rate(db) is None

        # The write path's invalidation clears it; the next read reflects the DB.
        await invalidate_tax()
        assert await get_global_tax_rate(db) == 20.0


async def test_master_set_tax_rate_invalidates(client):
    _user, token = await _master(client)
    # Seed the cache with the default-rate answer.
    r = await client.get("/api/v1/tenant/tax-rate", headers=auth_headers(token))
    assert r.status_code == 200 and r.json()["is_global"] is False

    # Master sets a global rate via the real endpoint (which invalidates).
    r = await client.put(
        "/api/v1/tenant/master/tax-rate",
        headers=auth_headers(token),
        json={"tax_rate": 17.5},
    )
    assert r.status_code == 200

    # The re-read reflects the new rate rather than the cached default.
    r = await client.get("/api/v1/tenant/tax-rate", headers=auth_headers(token))
    assert r.json() == {"tax_rate": 17.5, "is_global": True}


# ---------------- Feature entitlements: cached + invalidated ----------------

async def test_feature_enabled_cached_until_invalidated():
    client_id = 909090
    async with db_manager.async_session_maker() as db:
        # No row => enabled by default; this caches True.
        assert await is_feature_enabled(db, client_id, "loyalty") is True

        # Disable it directly in the DB, behind the cache's back.
        db.add(
            Client_features(
                user_id=str(uuid.uuid4()),
                client_id=client_id,
                feature_name="loyalty",
                is_enabled=False,
            )
        )
        await db.commit()

        # Still cached as enabled.
        assert await is_feature_enabled(db, client_id, "loyalty") is True

        # Invalidate the client's entitlements -> the gate now sees it disabled.
        await invalidate_features(client_id)
        assert await is_feature_enabled(db, client_id, "loyalty") is False


# ---------------- Brand: cached by domain + invalidated on write ----------------

async def test_branding_by_domain_cached_and_invalidated_on_logo(client):
    _user, token, agent_id = await make_agent_account(client)
    domain = f"brand-{uuid.uuid4().hex[:8]}.example.com"
    async with db_manager.async_session_maker() as db:
        agent = await db.get(Agents, agent_id)
        agent.custom_domain = domain
        agent.company_name = "Before Co"
        await db.commit()

    # Public by-domain read — caches the brand under the domain key.
    r = await client.get(f"/api/v1/tenant/branding/by-domain?domain={domain}")
    assert r.status_code == 200 and r.json()["company_name"] == "Before Co"

    # Change the brand straight in the DB — the cache should still serve the old.
    async with db_manager.async_session_maker() as db:
        agent = await db.get(Agents, agent_id)
        agent.company_name = "After Co"
        await db.commit()
    r = await client.get(f"/api/v1/tenant/branding/by-domain?domain={domain}")
    assert r.json()["company_name"] == "Before Co"  # served from cache

    # An agent-facing branding write goes through the invalidation path.
    r = await client.put(
        "/api/v1/branding/update",
        headers=auth_headers(token),
        json={"primary_color": "#000000"},
    )
    assert r.status_code == 200

    # The domain key was cleared, so the public read now reflects the DB.
    r = await client.get(f"/api/v1/tenant/branding/by-domain?domain={domain}")
    assert r.json()["company_name"] == "After Co"


async def test_branding_by_domain_negative_lookup_not_cached(client):
    missing = f"nobody-{uuid.uuid4().hex[:8]}.example.com"
    r = await client.get(f"/api/v1/tenant/branding/by-domain?domain={missing}")
    assert r.status_code == 404
    # A 404 must not have populated the cache (no negative caching).
    assert await cache.get_json(brand_domain_key(missing)) is None


# ---------------- Dashboard aggregates: cached + invalidated ----------------

async def test_dashboard_products_count_invalidated_on_product_write(client):
    user, token, client_id = await make_client_account(client)

    r = await client.get("/api/v1/tenant/client/dashboard", headers=auth_headers(token))
    assert r.status_code == 200 and r.json()["products_count"] == 0

    # The zero snapshot is now cached for this client.
    assert await cache.get_json(dashboard_key(client_id)) is not None

    # Create a product through the service (its write path invalidates).
    async with db_manager.async_session_maker() as db:
        await ProductsService(db).create(
            {"client_id": client_id, "name": "Widget", "price": 9.0},
            user_id=user["id"],
        )

    # The snapshot was cleared, so the re-read recomputes the new count.
    r = await client.get("/api/v1/tenant/client/dashboard", headers=auth_headers(token))
    assert r.json()["products_count"] == 1


async def _master(client):
    from tests.conftest import make_master_account

    return await make_master_account(client)
