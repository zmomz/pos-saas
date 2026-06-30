"""#220 (M4·Inventory multi-branch): branch-level promotions.

A chain configures auto-applied promotions once (ISSUE-058). By default every
active promotion runs at every branch. A branch may **opt out** of a specific
promotion (e.g. a clearance promo that should not run at the flagship store);
resolving a branch's effective promotion set returns all active chain promotions
minus the ones that branch has disabled. Overrides are owner-scoped (SEC-02) and
one-per-(branch, promotion) — upserted, never duplicated. Re-enabling toggles the
same override row back on.

Sale-time enforcement (pricing a branch sale against its resolved set) is the
"then expand" follow-up; this slice resolves the effective set only, mirroring the
branch-pricing/branch-tax tracers.
"""
import pytest

from conftest import auth_headers, make_client_account


async def _make_branch(client, headers, name):
    resp = await client.post(
        "/api/v1/entities/branches",
        json={"name": name, "is_active": True},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _make_promo(client, headers, name):
    resp = await client.post(
        "/api/v1/entities/promotions",
        json={"name": name, "kind": "category", "disc_type": "percentage",
              "value": 10.0, "category": "drinks", "is_active": True},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _set_branch_promo(client, headers, branch_id, promo_id, is_enabled):
    resp = await client.put(
        f"/api/v1/pos/branches/{branch_id}/promotions/{promo_id}",
        json={"is_enabled": is_enabled},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _resolve(client, headers, branch_id):
    resp = await client.get(
        f"/api/v1/pos/branches/{branch_id}/promotions/resolve",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_branch_inherits_all_active_promotions_by_default(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    branch = await _make_branch(client, headers, "Flagship")
    p1 = await _make_promo(client, headers, "Drinks 10%")
    p2 = await _make_promo(client, headers, "Snacks 5%")

    resolved = await _resolve(client, headers, branch)
    ids = {p["promotion_id"] for p in resolved["promotions"]}
    assert ids == {p1, p2}
    assert resolved["disabled_promotion_ids"] == []


@pytest.mark.asyncio
async def test_branch_can_disable_a_promotion_per_branch(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    branch_a = await _make_branch(client, headers, "Flagship")
    branch_b = await _make_branch(client, headers, "Outlet")
    p1 = await _make_promo(client, headers, "Clearance")
    p2 = await _make_promo(client, headers, "Drinks 10%")

    # Disable the clearance promo at branch A only.
    await _set_branch_promo(client, headers, branch_a, p1, False)

    resolved_a = await _resolve(client, headers, branch_a)
    assert {p["promotion_id"] for p in resolved_a["promotions"]} == {p2}
    assert resolved_a["disabled_promotion_ids"] == [p1]

    # Branch B is untouched — it still runs both promotions.
    resolved_b = await _resolve(client, headers, branch_b)
    assert {p["promotion_id"] for p in resolved_b["promotions"]} == {p1, p2}
    assert resolved_b["disabled_promotion_ids"] == []


@pytest.mark.asyncio
async def test_set_is_idempotent_upsert_and_can_reenable(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    branch = await _make_branch(client, headers, "Flagship")
    p1 = await _make_promo(client, headers, "Clearance")

    await _set_branch_promo(client, headers, branch, p1, False)
    # Toggling back on updates the same override row rather than inserting a dup.
    await _set_branch_promo(client, headers, branch, p1, True)

    resolved = await _resolve(client, headers, branch)
    assert {p["promotion_id"] for p in resolved["promotions"]} == {p1}
    assert resolved["disabled_promotion_ids"] == []


@pytest.mark.asyncio
async def test_delete_override_falls_back_to_enabled(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    branch = await _make_branch(client, headers, "Flagship")
    p1 = await _make_promo(client, headers, "Clearance")

    await _set_branch_promo(client, headers, branch, p1, False)
    resp = await client.delete(
        f"/api/v1/pos/branches/{branch}/promotions/{p1}", headers=headers
    )
    assert resp.status_code == 200, resp.text

    resolved = await _resolve(client, headers, branch)
    assert {p["promotion_id"] for p in resolved["promotions"]} == {p1}
    assert resolved["disabled_promotion_ids"] == []


@pytest.mark.asyncio
async def test_override_is_owner_scoped(client):
    """A second tenant's branch promotion override never leaks into the first
    tenant's resolution, and a tenant only ever resolves its own promotions
    (SEC-02)."""
    user_a, token_a, cid_a = await make_client_account(client)
    headers_a = auth_headers(token_a)
    branch_a = await _make_branch(client, headers_a, "A-Flagship")
    pa = await _make_promo(client, headers_a, "A-Clearance")
    await _set_branch_promo(client, headers_a, branch_a, pa, False)

    user_b, token_b, cid_b = await make_client_account(client)
    headers_b = auth_headers(token_b)

    # Tenant B resolving tenant A's branch id sees none of A's promotions and no
    # overrides — strict tenant isolation.
    resolved_b = await _resolve(client, headers_b, branch_a)
    assert resolved_b["promotions"] == []
    assert resolved_b["disabled_promotion_ids"] == []
