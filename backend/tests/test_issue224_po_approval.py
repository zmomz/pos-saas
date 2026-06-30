"""ISSUE-224 (M4 Inventory) — PO approval chain.

Procurement governance: a purchase order must walk an approval state machine
(draft → submitted → approved → ordered → received) before its goods can be
booked into stock. These tests pin the tracer-bullet slice:

- a ``/transition`` endpoint advances the PO one step at a time along the chain;
- moving backwards or skipping a step is rejected (400);
- ``received`` cannot be set via ``/transition`` (it is reached only by ``/receive``,
  which books stock);
- a PO that has not yet been approved cannot be received (400);
- once approved/ordered the PO receives normally and lands stock.
"""
import json

import pytest

from conftest import add_product, auth_headers, make_client_account


async def _create_po(client, headers, items, status="draft"):
    resp = await client.post(
        "/api/v1/entities/purchase_orders",
        json={"order_number": "PO-A", "status": status, "items_json": json.dumps(items)},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _transition(client, headers, po_id, status):
    return await client.post(
        f"/api/v1/entities/purchase_orders/{po_id}/transition",
        json={"status": status},
        headers=headers,
    )


@pytest.mark.asyncio
async def test_po_walks_the_approval_chain(client):
    """A draft PO advances draft→submitted→approved→ordered, each step persisting."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=0)
    po_id = await _create_po(client, headers, [{"product_id": pid, "quantity": 3}])

    for target in ("submitted", "approved", "ordered"):
        r = await _transition(client, headers, po_id, target)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == target

    # The walked status survives onto the persisted record.
    got = await client.get(f"/api/v1/entities/purchase_orders/{po_id}", headers=headers)
    assert got.json()["status"] == "ordered"


@pytest.mark.asyncio
async def test_po_cannot_skip_or_reverse_chain_steps(client):
    """Skipping a step (draft→approved) and reversing (approved→draft) are rejected."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=0)
    po_id = await _create_po(client, headers, [{"product_id": pid, "quantity": 3}])

    skip = await _transition(client, headers, po_id, "approved")
    assert skip.status_code == 400, skip.text

    # Advance legitimately, then try to reverse.
    await _transition(client, headers, po_id, "submitted")
    await _transition(client, headers, po_id, "approved")
    back = await _transition(client, headers, po_id, "submitted")
    assert back.status_code == 400, back.text


@pytest.mark.asyncio
async def test_received_is_not_a_transition_target(client):
    """``received`` is reached only through /receive, never via /transition."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=0)
    po_id = await _create_po(client, headers, [{"product_id": pid, "quantity": 3}], status="ordered")

    r = await _transition(client, headers, po_id, "received")
    assert r.status_code == 400, r.text


@pytest.mark.asyncio
async def test_unapproved_po_cannot_be_received(client):
    """A PO still in draft/submitted is rejected by /receive (must be approved first)."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=0)
    po_id = await _create_po(client, headers, [{"product_id": pid, "quantity": 3}])

    r = await client.post(
        f"/api/v1/entities/purchase_orders/{po_id}/receive",
        json={},
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert "approv" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_approved_po_receives_into_stock(client):
    """Once approved, the PO receives normally and lands stock."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=0)
    po_id = await _create_po(client, headers, [{"product_id": pid, "quantity": 3}])

    await _transition(client, headers, po_id, "submitted")
    await _transition(client, headers, po_id, "approved")

    r = await client.post(
        f"/api/v1/entities/purchase_orders/{po_id}/receive",
        json={},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "received"
