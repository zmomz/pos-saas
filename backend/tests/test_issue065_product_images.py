"""ISSUE-065 (P2 catalog): product images — upload + persisted reference.

A merchant uploads an image for one of their products; the served URL is
persisted on the product and surfaces in the catalog/POS list payload (so the
POS tile grid and the management screen can render it). Validation rejects
non-image types and oversized files; uploads are owner-scoped.

Mirrors the agent-logo upload pattern (AG-01): the file is stored locally under
``uploads/products/`` and served from ``/uploads`` — the S3-backed object store
(routers/storage.py, ISSUE-030) remains available for cloud deployments.
"""
import pytest

from tests.conftest import auth_headers, make_client_account

pytestmark = pytest.mark.asyncio

# Bytes are never decoded as a real image — the endpoint validates the declared
# content-type and size only, so any payload with an image MIME type is fine.
_FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"fake-png-bytes"


async def _create_product(client, token, name="Latte", price=12.0):
    resp = await client.post(
        "/api/v1/products/create",
        json={"name": name, "price": price},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_upload_product_image_persists_reference(client):
    """Upload → reference persisted → renders in the list payload."""
    _user, token, _client_id = await make_client_account(client)
    product = await _create_product(client, token)
    assert product["image_url"] is None
    pid = product["id"]

    resp = await client.post(
        f"/api/v1/products/{pid}/image",
        files={"file": ("latte.png", _FAKE_PNG, "image/png")},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["image_url"]
    assert body["image_url"].startswith("/uploads/products/")

    # The reference is persisted and surfaces wherever products are listed
    # (catalog management + POS tile grid both read this payload).
    resp = await client.get("/api/v1/products/list", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    match = next(p for p in resp.json()["items"] if p["id"] == pid)
    assert match["image_url"] == body["image_url"]


async def test_upload_rejects_non_image_type(client):
    """A non-image content type is rejected (400) and nothing is persisted."""
    _user, token, _client_id = await make_client_account(client)
    pid = (await _create_product(client, token))["id"]

    resp = await client.post(
        f"/api/v1/products/{pid}/image",
        files={"file": ("notes.txt", b"plain text, not an image", "text/plain")},
        headers=auth_headers(token),
    )
    assert resp.status_code == 400, resp.text

    resp = await client.get("/api/v1/products/list", headers=auth_headers(token))
    match = next(p for p in resp.json()["items"] if p["id"] == pid)
    assert match["image_url"] is None


async def test_upload_rejects_oversized_image(client):
    """An image past the 2 MB cap is rejected (413)."""
    _user, token, _client_id = await make_client_account(client)
    pid = (await _create_product(client, token))["id"]

    too_big = b"\x89PNG\r\n\x1a\n" + b"x" * (2 * 1024 * 1024 + 1)
    resp = await client.post(
        f"/api/v1/products/{pid}/image",
        files={"file": ("huge.png", too_big, "image/png")},
        headers=auth_headers(token),
    )
    assert resp.status_code == 413, resp.text


async def test_upload_is_owner_scoped(client):
    """A client cannot attach an image to another merchant's product (404)."""
    _user_a, token_a, _client_a = await make_client_account(client)
    pid_a = (await _create_product(client, token_a))["id"]

    _user_b, token_b, _client_b = await make_client_account(client)
    resp = await client.post(
        f"/api/v1/products/{pid_a}/image",
        files={"file": ("x.png", _FAKE_PNG, "image/png")},
        headers=auth_headers(token_b),
    )
    assert resp.status_code == 404, resp.text
