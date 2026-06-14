"""ISSUE-030 — object storage: make it work (no longer a 500 façade).

`StorageService` reads `settings.oss_service_url` / `oss_api_key`. Before this
slice those keys did not exist on `Settings`, so construction raised an
`AttributeError` the router did not catch → every storage endpoint answered 500.

These behaviours are pinned through the public HTTP API:

* with OSS unconfigured the endpoints degrade to a clear 503 (never a raw 500);
* with OSS configured (gateway mocked) a request returns 200 with real data;
* the CSV report export is a real caller — it hands back a presigned storage
  upload URL when storage is configured, and degrades to ``null`` otherwise.
"""
import pytest
from conftest import auth_headers, make_client_account, register_user
from core.config import settings


@pytest.fixture
def configured_oss(monkeypatch):
    """Pretend the OSS gateway is configured for the duration of a test."""
    monkeypatch.setattr(settings, "oss_service_url", "http://oss.test/")
    monkeypatch.setattr(settings, "oss_api_key", "test-key")


def mock_oss_gateway(monkeypatch, data):
    """Stub the object-storage service's single network chokepoint
    (``_arequest_oss_service`` returns the gateway's ``data`` payload) so a
    request exercises the real service code without a live OSS server. Patching
    here — not ``httpx.AsyncClient`` — avoids clobbering the ASGI test client,
    which shares the same httpx transport."""

    async def _fake_request(self, method, endpoint, params=None, payload=None):
        return data

    monkeypatch.setattr("services.storage.StorageService._arequest_oss_service", _fake_request)


async def test_storage_endpoint_returns_503_when_unconfigured(client):
    # No OSS_SERVICE_URL / OSS_API_KEY set: storage degrades to a clear 503,
    # never an unhandled 500.
    _user, token, _ = await register_user(client)
    resp = await client.get("/api/v1/storage/list-buckets", headers=auth_headers(token))
    assert resp.status_code == 503, resp.text


async def test_storage_endpoint_returns_data_when_configured(client, configured_oss, monkeypatch):
    # With OSS configured (gateway mocked) a valid request returns 200 + data,
    # not a 500.
    _user, token, _ = await register_user(client)
    mock_oss_gateway(monkeypatch, {"buckets": [{"bucket_name": "receipts", "visibility": "public"}]})
    resp = await client.get("/api/v1/storage/list-buckets", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    assert resp.json()["buckets"][0]["bucket_name"] == "receipts"


async def test_csv_export_returns_storage_upload_url_when_configured(client, configured_oss, monkeypatch):
    # The CSV report export is a real caller of StorageService: with storage
    # configured it hands back a presigned upload URL so the merchant can
    # archive the export to object storage.
    _user, token, _client_id = await make_client_account(client)
    mock_oss_gateway(
        monkeypatch,
        {"upload_url": "https://oss.test/presigned-put", "expires_at": "2099-01-01T00:00:00Z"},
    )
    resp = await client.get("/api/v1/reports/export-csv?days=30", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["csv_content"].startswith("Invoice Number")
    assert body["storage_upload_url"] == "https://oss.test/presigned-put"


async def test_csv_export_degrades_to_null_upload_url_when_unconfigured(client):
    # With storage unconfigured the export still works; the upload URL is simply
    # null (no 500, no dependency on the OSS gateway).
    _user, token, _client_id = await make_client_account(client)
    resp = await client.get("/api/v1/reports/export-csv?days=30", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "csv_content" in body
    assert body["storage_upload_url"] is None
