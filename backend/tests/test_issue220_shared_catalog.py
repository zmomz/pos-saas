"""#220 (M4·Inventory multi-branch): shared catalog management across branches.

A multi-location chain manages ONE shared product catalog centrally. By default
every active chain product is available at every branch (permissive — single-branch
installs are unaffected). A branch may opt a product **out** of its local catalog
(e.g. an outlet that doesn't carry a premium line) by disabling it for that branch;
resolving a branch's effective catalog returns all active chain products minus the
ones that branch has disabled. Overrides are owner-scoped (SEC-02) and
one-per-(branch, product) — upserted, never duplicated. Re-enabling toggles the
same override row back on.

This mirrors the branch-promotions opt-out tracer: it resolves the effective
catalog only; sale-time enforcement (rejecting a line for a product a branch has
opted out of) is a "then expand" follow-up.
"""
import pytest

from conftest import add_product, auth_headers, make_client_account


async def _make_branch(client, headers, name):
    resp = await client.post(
        "/api/v1/entities/branches",
        json={"name": name, "is_active": True},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _set_branch_catalog(client, headers, branch_id, product_id, is_available):
    resp = await client.put(
        f"/api/v1/pos/branches/{branch_id}/catalog/{product_id}",
        json={"is_available": is_available},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _resolve(client, headers, branch_id):
    resp = await client.get(
        f"/api/v1/pos/branches/{branch_id}/catalog/resolve",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_branch_inherits_full_shared_catalog_by_default(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    branch = await _make_branch(client, headers, "Flagship")
    p1 = await add_product(client_id, user["id"], name="Water", price=2.0)
    p2 = await add_product(client_id, user["id"], name="Coffee", price=12.0)

    resolved = await _resolve(client, headers, branch)
    ids = {p["product_id"] for p in resolved["products"]}
    assert ids == {p1, p2}
    assert resolved["disabled_product_ids"] == []


@pytest.mark.asyncio
async def test_branch_can_opt_a_product_out_per_branch(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    branch_a = await _make_branch(client, headers, "Flagship")
    branch_b = await _make_branch(client, headers, "Outlet")
    p1 = await add_product(client_id, user["id"], name="Premium Line", price=99.0)
    p2 = await add_product(client_id, user["id"], name="Water", price=2.0)

    # Outlet does not carry the premium line.
    await _set_branch_catalog(client, headers, branch_a, p1, False)

    resolved_a = await _resolve(client, headers, branch_a)
    assert {p["product_id"] for p in resolved_a["products"]} == {p2}
    assert resolved_a["disabled_product_ids"] == [p1]

    # Branch B is untouched — it still carries the full shared catalog.
    resolved_b = await _resolve(client, headers, branch_b)
    assert {p["product_id"] for p in resolved_b["products"]} == {p1, p2}
    assert resolved_b["disabled_product_ids"] == []


@pytest.mark.asyncio
async def test_set_is_idempotent_upsert_and_can_reenable(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    branch = await _make_branch(client, headers, "Flagship")
    p1 = await add_product(client_id, user["id"], name="Premium Line", price=99.0)

    await _set_branch_catalog(client, headers, branch, p1, False)
    # Re-stocking the line at the branch updates the same override row, no dup.
    await _set_branch_catalog(client, headers, branch, p1, True)

    resolved = await _resolve(client, headers, branch)
    assert {p["product_id"] for p in resolved["products"]} == {p1}
    assert resolved["disabled_product_ids"] == []


@pytest.mark.asyncio
async def test_delete_override_falls_back_to_available(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    branch = await _make_branch(client, headers, "Flagship")
    p1 = await add_product(client_id, user["id"], name="Premium Line", price=99.0)

    await _set_branch_catalog(client, headers, branch, p1, False)
    resp = await client.delete(
        f"/api/v1/pos/branches/{branch}/catalog/{p1}", headers=headers
    )
    assert resp.status_code == 200, resp.text

    resolved = await _resolve(client, headers, branch)
    assert {p["product_id"] for p in resolved["products"]} == {p1}
    assert resolved["disabled_product_ids"] == []


@pytest.mark.asyncio
async def test_inactive_chain_products_are_excluded_from_shared_catalog(client):
    """An archived/inactive chain product is not part of the shared catalog any
    branch resolves (mirrors the chain-wide ``is_active`` gate)."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    branch = await _make_branch(client, headers, "Flagship")
    active = await add_product(client_id, user["id"], name="Water", price=2.0)
    archived = await add_product(client_id, user["id"], name="Retired SKU", price=5.0)

    from sqlalchemy import update as sa_update
    from conftest import db_manager
    from models.products import Products

    async with db_manager.async_session_maker() as db:
        await db.execute(
            sa_update(Products).where(Products.id == archived).values(is_active=False)
        )
        await db.commit()

    resolved = await _resolve(client, headers, branch)
    assert {p["product_id"] for p in resolved["products"]} == {active}


@pytest.mark.asyncio
async def test_override_is_owner_scoped(client):
    """A second tenant's branch catalog override never leaks into the first
    tenant's resolution, and a tenant only ever resolves its own catalog
    (SEC-02)."""
    user_a, token_a, cid_a = await make_client_account(client)
    headers_a = auth_headers(token_a)
    branch_a = await _make_branch(client, headers_a, "A-Flagship")
    pa = await add_product(cid_a, user_a["id"], name="A-Water", price=2.0)
    await _set_branch_catalog(client, headers_a, branch_a, pa, False)

    user_b, token_b, cid_b = await make_client_account(client)
    headers_b = auth_headers(token_b)

    # Tenant B resolving tenant A's branch id sees none of A's catalog and no
    # overrides — strict tenant isolation.
    resolved_b = await _resolve(client, headers_b, branch_a)
    assert resolved_b["products"] == []
    assert resolved_b["disabled_product_ids"] == []
