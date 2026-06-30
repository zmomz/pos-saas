"""CL-02 (F-027): the client picks their business type during first-login setup.

The agent seeds a default ``business_type`` at provisioning; the merchant then
confirms/changes it on their **own** account via the client-self endpoint that
the first-login screen calls. The selection drives retail vs restaurant POS mode
and gates the restaurant vertical (RST-*).

These tests pin:
  * provisioning persists the chosen business type (readable via /client/profile);
  * a client can set their own business type (force-reset can set it);
  * an invalid value is rejected (400);
  * the write is scoped to the caller's own client row (a non-client → 403, and
    one client can never change another client's business type — SEC-02).
"""
import pytest

from conftest import auth_headers, make_agent_account, make_client_account


@pytest.mark.asyncio
async def test_client_profile_reflects_provisioned_business_type(client):
    """Provisioning persists business_type → the client reads it back."""
    _user, token, _cid = await make_client_account(client, business_type="restaurant")

    resp = await client.get(
        "/api/v1/tenant/client/profile", headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["business_type"] == "restaurant"


@pytest.mark.asyncio
async def test_client_sets_own_business_type_at_first_login(client):
    """A client changes their own business type (retail → both) and it persists."""
    _user, token, _cid = await make_client_account(client, business_type="retail")

    resp = await client.post(
        "/api/v1/tenant/client/business-type",
        json={"business_type": "both"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["business_type"] == "both"

    # Persisted: a fresh read returns the new value.
    profile = await client.get(
        "/api/v1/tenant/client/profile", headers=auth_headers(token)
    )
    assert profile.status_code == 200, profile.text
    assert profile.json()["business_type"] == "both"


@pytest.mark.asyncio
async def test_invalid_business_type_rejected(client):
    """An unknown business type is rejected up-front (400), not silently stored."""
    _user, token, _cid = await make_client_account(client, business_type="retail")

    resp = await client.post(
        "/api/v1/tenant/client/business-type",
        json={"business_type": "bistro"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 400, resp.text

    # The original value is untouched.
    profile = await client.get(
        "/api/v1/tenant/client/profile", headers=auth_headers(token)
    )
    assert profile.json()["business_type"] == "retail"


@pytest.mark.asyncio
async def test_non_client_cannot_set_business_type(client):
    """An agent (no client row) cannot reach the client-self business-type endpoint."""
    _user, token, _aid = await make_agent_account(client)

    resp = await client.post(
        "/api/v1/tenant/client/business-type",
        json={"business_type": "restaurant"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_client_only_changes_own_business_type(client):
    """SEC-02: setting one client's business type never affects another client."""
    _u1, token1, _c1 = await make_client_account(client, business_type="retail")
    _u2, token2, _c2 = await make_client_account(client, business_type="retail")

    resp = await client.post(
        "/api/v1/tenant/client/business-type",
        json={"business_type": "restaurant"},
        headers=auth_headers(token1),
    )
    assert resp.status_code == 200, resp.text

    # Client 1 changed; client 2 is unaffected.
    p1 = await client.get("/api/v1/tenant/client/profile", headers=auth_headers(token1))
    p2 = await client.get("/api/v1/tenant/client/profile", headers=auth_headers(token2))
    assert p1.json()["business_type"] == "restaurant"
    assert p2.json()["business_type"] == "retail"


@pytest.mark.asyncio
async def test_change_type_recomputes_restaurant_feature_without_data_loss(client):
    """Issue #201 change-type flow: switching business_type recomputes the
    type-driven ``restaurant`` feature flag in lock-step, and switching back
    restores access — no data is deleted, only the flag is realigned.

    A ``both`` client reaches the restaurant vertical (type ok + feature
    enabled-by-default). Switching to ``retail`` blocks it; switching back to
    ``both`` must re-enable the feature the recompute disabled, otherwise the
    left-behind ``is_enabled=False`` row would keep 403-ing by feature even
    though the type now allows it.
    """
    _user, token, _cid = await make_client_account(client, business_type="both")
    headers = auth_headers(token)

    # Reachable to start with.
    assert (await client.get("/api/v1/restaurant/tables", headers=headers)).status_code == 200

    # Switch to retail → type gate blocks it.
    r = await client.post(
        "/api/v1/tenant/client/business-type",
        json={"business_type": "retail"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert (await client.get("/api/v1/restaurant/tables", headers=headers)).status_code == 403

    # Switch back to both → the recompute must re-enable the restaurant feature
    # flag it disabled, so access is restored.
    r = await client.post(
        "/api/v1/tenant/client/business-type",
        json={"business_type": "both"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert (await client.get("/api/v1/restaurant/tables", headers=headers)).status_code == 200
