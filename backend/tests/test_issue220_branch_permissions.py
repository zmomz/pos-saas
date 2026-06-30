"""#220 (M4·Inventory multi-branch): per-branch staff access scoping.

A chain's staff member may be scoped to a subset of its branches. The rule is
deliberately permissive-by-default so existing single-branch installs keep
working: a staff member with *no* branch assignments has chain-wide access (every
branch), while assigning even one branch flips them to *scoped* — reachable only
at the branches explicitly granted. Revoking the last assignment restores
chain-wide access. Every assignment is owner-scoped (SEC-02) and one row per
(staff, branch) — upserted, never duplicated.
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


async def _make_staff(client, headers, name="Cashier"):
    resp = await client.post(
        "/api/v1/entities/staff_members",
        json={"name": name, "email": f"{name.lower()}@shop.test", "role": "cashier"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _assign(client, headers, staff_id, branch_id):
    resp = await client.put(
        f"/api/v1/pos/staff/{staff_id}/branches/{branch_id}",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _revoke(client, headers, staff_id, branch_id):
    resp = await client.delete(
        f"/api/v1/pos/staff/{staff_id}/branches/{branch_id}",
        headers=headers,
    )
    return resp


async def _list(client, headers, staff_id):
    resp = await client.get(
        f"/api/v1/pos/staff/{staff_id}/branches",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _access(client, headers, staff_id, branch_id):
    resp = await client.get(
        f"/api/v1/pos/staff/{staff_id}/branches/{branch_id}/access",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_unscoped_staff_has_chain_wide_access(client):
    """A staff member with no assignments reaches every branch (default-open)."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    branch_a = await _make_branch(client, headers, "Airport")
    branch_b = await _make_branch(client, headers, "Suburb")
    staff = await _make_staff(client, headers)

    listing = await _list(client, headers, staff)
    assert listing["scoped"] is False
    assert listing["branch_ids"] == []

    for b in (branch_a, branch_b):
        acc = await _access(client, headers, staff, b)
        assert acc["has_access"] is True
        assert acc["scoped"] is False


@pytest.mark.asyncio
async def test_assigning_a_branch_scopes_access_to_it(client):
    """Once assigned, the staff member reaches the assigned branch but not others."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    branch_a = await _make_branch(client, headers, "Airport")
    branch_b = await _make_branch(client, headers, "Suburb")
    staff = await _make_staff(client, headers)

    assigned = await _assign(client, headers, staff, branch_a)
    assert assigned["assigned"] is True
    assert assigned["branch_id"] == branch_a

    listing = await _list(client, headers, staff)
    assert listing["scoped"] is True
    assert listing["branch_ids"] == [branch_a]

    granted = await _access(client, headers, staff, branch_a)
    assert granted["has_access"] is True
    assert granted["scoped"] is True

    denied = await _access(client, headers, staff, branch_b)
    assert denied["has_access"] is False
    assert denied["scoped"] is True


@pytest.mark.asyncio
async def test_assign_is_idempotent_upsert(client):
    """Assigning the same branch twice does not duplicate the grant."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    branch_a = await _make_branch(client, headers, "Airport")
    staff = await _make_staff(client, headers)

    await _assign(client, headers, staff, branch_a)
    await _assign(client, headers, staff, branch_a)

    listing = await _list(client, headers, staff)
    assert listing["branch_ids"] == [branch_a]


@pytest.mark.asyncio
async def test_revoking_last_branch_restores_chain_wide_access(client):
    """Removing the only assignment flips the staff member back to unscoped."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    branch_a = await _make_branch(client, headers, "Airport")
    branch_b = await _make_branch(client, headers, "Suburb")
    staff = await _make_staff(client, headers)

    await _assign(client, headers, staff, branch_a)
    resp = await _revoke(client, headers, staff, branch_a)
    assert resp.status_code == 200, resp.text
    assert resp.json()["removed"] is True

    listing = await _list(client, headers, staff)
    assert listing["scoped"] is False
    # Back to default-open: every branch reachable again.
    assert (await _access(client, headers, staff, branch_b))["has_access"] is True

    # Revoking a branch that was never assigned is a 404 (nothing to remove).
    missing = await _revoke(client, headers, staff, branch_b)
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_assignments_are_owner_scoped(client):
    """A second tenant cannot see or assign another tenant's staff branches (SEC-02)."""
    owner, token, _ = await make_client_account(client)
    headers = auth_headers(token)
    branch_a = await _make_branch(client, headers, "Airport")
    staff = await _make_staff(client, headers)
    await _assign(client, headers, staff, branch_a)

    other, other_token, _ = await make_client_account(client)
    other_headers = auth_headers(other_token)

    # The other tenant doesn't own this staff row → 404 on every path.
    assert (
        await client.get(f"/api/v1/pos/staff/{staff}/branches", headers=other_headers)
    ).status_code == 404
    assert (
        await client.put(
            f"/api/v1/pos/staff/{staff}/branches/{branch_a}", headers=other_headers
        )
    ).status_code == 404
    assert (
        await client.get(
            f"/api/v1/pos/staff/{staff}/branches/{branch_a}/access",
            headers=other_headers,
        )
    ).status_code == 404
