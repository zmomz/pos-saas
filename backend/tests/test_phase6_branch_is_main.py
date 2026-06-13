"""ISSUE-062 — designate the main branch (exactly one).

The ``branches`` model carries ``is_main`` but nothing enforced the
"exactly one main branch" invariant: the generic CRUD update could flip
``is_main`` on any number of branches independently. These tests pin a
dedicated set-main action that marks one branch as main and unsets every
other branch the owner has, atomically — so there is always at most one.

Owner-scoped (SEC-02): a tenant cannot set-main on another tenant's branch.
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


async def _branches_by_id(client, headers):
    resp = await client.get("/api/v1/entities/branches", headers=headers)
    assert resp.status_code == 200, resp.text
    return {b["id"]: b for b in resp.json()["items"]}


@pytest.mark.asyncio
async def test_set_main_unsets_the_previous_main(client):
    """Setting a new main branch unsets the previously-main one (persisted)."""
    user, token, _client_id = await make_client_account(client)
    headers = auth_headers(token)
    a = await _make_branch(client, headers, "Main")
    b = await _make_branch(client, headers, "Second")

    # Designate A as main.
    resp = await client.post(f"/api/v1/entities/branches/{a}/set-main", headers=headers)
    assert resp.status_code == 200, resp.text
    rows = await _branches_by_id(client, headers)
    assert rows[a]["is_main"] is True
    assert rows[b]["is_main"] is not True

    # Now designate B as main — A must be unset, exactly one main remains.
    resp = await client.post(f"/api/v1/entities/branches/{b}/set-main", headers=headers)
    assert resp.status_code == 200, resp.text
    rows = await _branches_by_id(client, headers)
    assert rows[b]["is_main"] is True
    assert rows[a]["is_main"] is not True
    assert sum(1 for r in rows.values() if r["is_main"]) == 1


@pytest.mark.asyncio
async def test_set_main_is_owner_scoped(client):
    """A tenant cannot set-main on another tenant's branch (SEC-02)."""
    user_a, token_a, _ = await make_client_account(client)
    headers_a = auth_headers(token_a)
    a_branch = await _make_branch(client, headers_a, "A-Main")
    resp = await client.post(f"/api/v1/entities/branches/{a_branch}/set-main", headers=headers_a)
    assert resp.status_code == 200, resp.text

    # A second, unrelated tenant tries to designate A's branch as main.
    _user_b, token_b, _ = await make_client_account(client)
    headers_b = auth_headers(token_b)
    resp = await client.post(f"/api/v1/entities/branches/{a_branch}/set-main", headers=headers_b)
    assert resp.status_code == 404, resp.text

    # A's branch is untouched — still main for A.
    rows_a = await _branches_by_id(client, headers_a)
    assert rows_a[a_branch]["is_main"] is True
