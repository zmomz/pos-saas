"""ISSUE-080 — working object storage: a merchant can generate and *download*
an export backed by object storage.

ISSUE-030 made ``StorageService`` work and wired a real caller that hands back a
presigned *upload* URL. That archives the export but the merchant still cannot
retrieve a stored file. This slice closes the round-trip: a new endpoint
generates the CSV, **stores it** in object storage, and returns a presigned
*download* URL the merchant can fetch.

Behaviours pinned through the public HTTP API:

* with OSS configured (gateway mocked) the export is stored and a download URL
  comes back — request export → file retrievable;
* the stored object key is owner-scoped to the requesting client;
* with OSS unconfigured the endpoint degrades to a clear 503 (never a 500);
* only clients may export (403 otherwise).
"""
import pytest
from conftest import auth_headers, make_client_account, make_master_account, register_user
from core.config import settings


@pytest.fixture
def configured_oss(monkeypatch):
    """Pretend the OSS gateway is configured for the duration of a test."""
    monkeypatch.setattr(settings, "oss_service_url", "http://oss.test/")
    monkeypatch.setattr(settings, "oss_api_key", "test-key")


def mock_oss_gateway(monkeypatch, captured=None):
    """Stub the OSS service's two network chokepoints: the JSON gateway
    (``_arequest_oss_service`` → presigned upload/download URLs) and the raw
    byte PUT to the presigned URL. Patching here, not ``httpx.AsyncClient``,
    avoids clobbering the ASGI test client that shares the transport."""

    async def _fake_request(self, method, endpoint, params=None, payload=None):
        return {
            "upload_url": "https://oss.test/presigned-put",
            "download_url": "https://oss.test/presigned-get",
            "expires_at": "2099-01-01T00:00:00Z",
        }

    async def _fake_put(self, url, content, content_type):
        if captured is not None:
            captured["url"] = url
            captured["content"] = content
            captured["content_type"] = content_type

    monkeypatch.setattr("services.storage.StorageService._arequest_oss_service", _fake_request)
    monkeypatch.setattr("services.storage.StorageService._aput_to_url", _fake_put)


async def test_export_download_stores_file_and_returns_download_url(client, configured_oss, monkeypatch):
    # Tracer bullet: a merchant requests an export; the CSV is uploaded to
    # object storage and a presigned download URL comes back so the file is
    # retrievable.
    _user, token, _client_id = await make_client_account(client)
    captured = {}
    mock_oss_gateway(monkeypatch, captured)

    resp = await client.get("/api/v1/reports/export-csv/download?days=30", headers=auth_headers(token))

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["download_url"] == "https://oss.test/presigned-get"
    assert body["object_key"].endswith(".csv")
    # The CSV bytes were actually uploaded to the presigned URL.
    assert captured["url"] == "https://oss.test/presigned-put"
    assert captured["content"].decode().startswith("Invoice Number")


async def test_export_download_object_key_is_owner_scoped(client, configured_oss, monkeypatch):
    # The stored object key is scoped to the requesting client so one merchant's
    # export can never collide with or be read as another's.
    _user, token, client_id = await make_client_account(client)
    mock_oss_gateway(monkeypatch)

    resp = await client.get("/api/v1/reports/export-csv/download?days=7", headers=auth_headers(token))

    assert resp.status_code == 200, resp.text
    assert str(client_id) in resp.json()["object_key"]


async def test_export_download_degrades_to_503_when_unconfigured(client):
    # With object storage unconfigured the stored-export endpoint degrades to a
    # clear 503 (service unavailable) — never an unhandled 500.
    _user, token, _client_id = await make_client_account(client)
    resp = await client.get("/api/v1/reports/export-csv/download", headers=auth_headers(token))
    assert resp.status_code == 503, resp.text


async def test_export_download_forbidden_for_non_client(client, configured_oss, monkeypatch):
    # Only client (merchant) accounts may export their data — a platform master
    # is not a merchant and is refused.
    _user, token = await make_master_account(client)
    mock_oss_gateway(monkeypatch)
    resp = await client.get("/api/v1/reports/export-csv/download", headers=auth_headers(token))
    assert resp.status_code == 403, resp.text
