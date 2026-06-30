"""#220 (M4·Inventory multi-branch): branch-level tax.

A chain applies a default VAT rate (the master's global rate, MA-05, else the
statutory 15 %); a branch may carry its own VAT rate. Resolving the effective
rate for a branch returns the branch override when one exists, else falls back to
that chain-wide effective rate. Overrides are owner-scoped (SEC-02) and
one-per-branch — upserted, never duplicated.

Sale-time enforcement (wiring this into checkout) is the "then expand"
follow-up; this slice resolves the rate only, mirroring the branch-pricing tracer.
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


async def _set_tax(client, headers, branch_id, vat_rate):
    resp = await client.put(
        f"/api/v1/pos/branches/{branch_id}/tax-rate",
        json={"vat_rate": vat_rate},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _resolve(client, headers, branch_id):
    resp = await client.get(
        f"/api/v1/pos/branches/{branch_id}/tax-rate/resolve",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_resolve_returns_branch_override(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    branch = await _make_branch(client, headers, "Airport")

    await _set_tax(client, headers, branch, 5.0)

    resolved = await _resolve(client, headers, branch)
    assert resolved["vat_rate"] == 5.0
    assert resolved["is_override"] is True


@pytest.mark.asyncio
async def test_resolve_falls_back_to_chain_rate(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    branch_a = await _make_branch(client, headers, "Airport")
    branch_b = await _make_branch(client, headers, "Suburb")

    # Override only branch A; branch B resolves to the chain-wide effective rate
    # (no global rate configured in a fresh tenant → statutory 15 %).
    await _set_tax(client, headers, branch_a, 5.0)

    resolved = await _resolve(client, headers, branch_b)
    assert resolved["vat_rate"] == 15.0
    assert resolved["is_override"] is False


@pytest.mark.asyncio
async def test_set_tax_is_idempotent_upsert(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    branch = await _make_branch(client, headers, "Airport")

    await _set_tax(client, headers, branch, 5.0)
    await _set_tax(client, headers, branch, 8.0)  # update, not insert

    listing = await client.get(
        f"/api/v1/pos/branches/{branch}/tax-rate", headers=headers
    )
    assert listing.status_code == 200, listing.text
    body = listing.json()
    assert body["vat_rate"] == 8.0
    assert body["is_override"] is True


@pytest.mark.asyncio
async def test_override_is_owner_scoped(client):
    """A second tenant's branch tax override never leaks into the first tenant's
    resolution (SEC-02)."""
    user_a, token_a, cid_a = await make_client_account(client)
    headers_a = auth_headers(token_a)
    branch_a = await _make_branch(client, headers_a, "A-Airport")
    await _set_tax(client, headers_a, branch_a, 5.0)

    user_b, token_b, cid_b = await make_client_account(client)
    headers_b = auth_headers(token_b)

    # Tenant B resolving tenant A's branch id sees no override — the chain rate.
    resolved_b = await _resolve(client, headers_b, branch_a)
    assert resolved_b["is_override"] is False
    assert resolved_b["vat_rate"] == 15.0
