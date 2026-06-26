"""ARC-11 — Validate enum router inputs.

Unknown discount ``type`` and printer ``paper_size``/``status`` values used to be
silently accepted at the router edge and then failed quietly downstream (a bogus
discount type was treated as a flat amount; an unknown paper size fell back to
80mm without telling the merchant). These tests pin the edge contract: the
documented enum values are accepted and anything else is rejected with 422.
"""
import uuid

from conftest import auth_headers, register_user


def _unique_code() -> str:
    return f"ARC11{uuid.uuid4().hex[:8].upper()}"


async def _create_discount(client, token, **fields):
    body = {"code": _unique_code(), "value": 10.0, **fields}
    return await client.post(
        "/api/v1/entities/discounts", json=body, headers=auth_headers(token)
    )


# ---------------------------------------------------------------------------
# Discount type
# ---------------------------------------------------------------------------
async def test_discount_accepts_known_types(client):
    _, token, _ = await register_user(client)
    for dtype in ("percentage", "fixed"):
        resp = await _create_discount(client, token, type=dtype)
        assert resp.status_code == 201, resp.text
        assert resp.json()["type"] == dtype


async def test_discount_rejects_unknown_type(client):
    _, token, _ = await register_user(client)
    resp = await _create_discount(client, token, type="bogus")
    assert resp.status_code == 422, resp.text


async def test_discount_update_rejects_unknown_type(client):
    _, token, _ = await register_user(client)
    created = await _create_discount(client, token, type="percentage")
    did = created.json()["id"]
    resp = await client.put(
        f"/api/v1/entities/discounts/{did}",
        json={"type": "bogus"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 422, resp.text


# ---------------------------------------------------------------------------
# Printer paper_size / status
# ---------------------------------------------------------------------------
async def _create_printer(client, token, **fields):
    body = {"name": "Front", "role": "receipt", **fields}
    return await client.post(
        "/api/v1/printers", json=body, headers=auth_headers(token)
    )


async def test_printer_accepts_known_paper_size_and_status(client):
    _, token, _ = await register_user(client)
    resp = await _create_printer(client, token, paper_size="58mm", status="inactive")
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["paper_size"] == "58mm"
    assert body["status"] == "inactive"


async def test_printer_rejects_unknown_paper_size(client):
    _, token, _ = await register_user(client)
    resp = await _create_printer(client, token, paper_size="A4")
    assert resp.status_code == 422, resp.text


async def test_printer_rejects_unknown_status(client):
    _, token, _ = await register_user(client)
    resp = await _create_printer(client, token, status="frozen")
    assert resp.status_code == 422, resp.text


async def test_printer_update_rejects_unknown_paper_size(client):
    _, token, _ = await register_user(client)
    created = await _create_printer(client, token, paper_size="80mm")
    pid = created.json()["id"]
    resp = await client.put(
        f"/api/v1/printers/{pid}",
        json={"paper_size": "A4"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 422, resp.text
