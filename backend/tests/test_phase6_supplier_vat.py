"""ISSUE-063: supplier VAT number — capture/store/display with format validation.

The ``suppliers.vat_number`` column already existed, but the create/update path
accepted any string. A Saudi VAT registration number (TRN) is exactly 15 digits
that begin and end with ``3``; an ill-formed number must be rejected with a clear
message at the entity-CRUD entry points, and a well-formed one must round-trip.
"""
import uuid

import pytest

from conftest import auth_headers, make_client_account


async def _create_supplier(client, token, **fields):
    body = {"name": f"Supplier-{uuid.uuid4().hex[:6]}", **fields}
    return await client.post(
        "/api/v1/entities/suppliers", json=body, headers=auth_headers(token)
    )


@pytest.mark.asyncio
async def test_create_supplier_rejects_malformed_vat_number(client):
    _owner, token, _client_id = await make_client_account(client)

    resp = await _create_supplier(client, token, vat_number="12345")

    assert resp.status_code == 422, resp.text
    # A clear, actionable message naming the 15-digit rule.
    assert "15" in resp.text


@pytest.mark.asyncio
async def test_create_supplier_stores_and_returns_valid_vat(client):
    _owner, token, _client_id = await make_client_account(client)

    # A well-formed Saudi TRN, surrounded by stray whitespace that is normalized.
    resp = await _create_supplier(client, token, vat_number="  300000000000003  ")
    assert resp.status_code == 201, resp.text
    supplier_id = resp.json()["id"]
    assert resp.json()["vat_number"] == "300000000000003"

    # It round-trips on a fresh GET (stored, not just echoed back).
    got = await client.get(
        f"/api/v1/entities/suppliers/{supplier_id}", headers=auth_headers(token)
    )
    assert got.status_code == 200, got.text
    assert got.json()["vat_number"] == "300000000000003"


@pytest.mark.asyncio
async def test_update_supplier_rejects_malformed_vat_number(client):
    _owner, token, _client_id = await make_client_account(client)
    created = await _create_supplier(client, token)
    assert created.status_code == 201, created.text
    supplier_id = created.json()["id"]

    resp = await client.put(
        f"/api/v1/entities/suppliers/{supplier_id}",
        json={"vat_number": "999"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 422, resp.text
    assert "15" in resp.text


@pytest.mark.asyncio
async def test_create_supplier_without_vat_is_allowed(client):
    """Existing/optional flows that omit the VAT number must keep working."""
    _owner, token, _client_id = await make_client_account(client)

    resp = await _create_supplier(client, token)

    assert resp.status_code == 201, resp.text
    assert resp.json()["vat_number"] is None
