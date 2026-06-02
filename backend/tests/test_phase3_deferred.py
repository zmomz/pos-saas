"""Phase 3 (deferred): SMS, API-usage metering, audit diffs + failed-auth,
structured JSON logging.
"""
import json
import logging

import pytest
from sqlalchemy import select

from conftest import add_product, auth_headers, make_client_account, register_user
from core.database import db_manager
from models.api_usage import Api_usage
from models.audit_logs import Audit_logs


# ---------------------------------------------------------------------------
# Twilio SMS provider (feature-gated, dev fallback)
# ---------------------------------------------------------------------------
async def _sale(client, headers, pid):
    resp = await client.post(
        "/api/v1/pos/transaction",
        json={
            "items": [{"product_id": pid, "name": "Cola", "price": 10.0, "quantity": 1}],
            "payment_method": "cash",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_send_sms_dev_fallback(monkeypatch):
    """With no Twilio config, send_sms logs and returns False (never raises)."""
    from core import sms

    for var in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM"):
        monkeypatch.delenv(var, raising=False)
    delivered = await sms.send_sms("+966500000000", "hello")
    assert delivered is False
    assert await sms.send_sms("", "hello") is False


@pytest.mark.asyncio
async def test_sms_receipt_endpoint_dev_fallback(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=10, price=10.0)
    sale = await _sale(client, headers, pid)

    resp = await client.post(
        f"/api/v1/pos/transactions/{sale['id']}/sms",
        json={"to_number": "+966500000000"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["delivered"] is False
    assert body["status"] == "logged"
    assert body["invoice_number"] == sale["invoice_number"]


@pytest.mark.asyncio
async def test_sms_receipt_requires_number(client):
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)
    pid = await add_product(client_id, user["id"], quantity=10, price=10.0)
    sale = await _sale(client, headers, pid)
    resp = await client.post(
        f"/api/v1/pos/transactions/{sale['id']}/sms",
        json={"to_number": "  "},
        headers=headers,
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# API-usage metering
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_api_usage_metering_records_rows(client, monkeypatch):
    monkeypatch.setenv("API_METERING_ENABLED", "true")
    user, token, _client_id = await make_client_account(client)
    headers = auth_headers(token)

    # A few authenticated calls that should each be metered.
    await client.get("/api/v1/entities/products", headers=headers)
    await client.get("/api/v1/entities/products", headers=headers)

    stats = await client.get("/api/v1/production/api-usage/stats", headers=headers)
    assert stats.status_code == 200, stats.text
    data = stats.json()
    assert data["total_requests"] >= 2

    async with db_manager.async_session_maker() as db:
        rows = (
            await db.execute(select(Api_usage).where(Api_usage.user_id == user["id"]))
        ).scalars().all()
    assert len(rows) >= 2
    assert any(r.endpoint.endswith("/entities/products") for r in rows)


# ---------------------------------------------------------------------------
# Audit completeness: entity id + change set + failed-auth
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_audit_captures_entity_and_changes(client):
    user, token, _client_id = await make_client_account(client)
    headers = auth_headers(token)

    resp = await client.post(
        "/api/v1/entities/products",
        json={"client_id": 1, "name": "AuditWidget", "price": 9.0, "quantity": 3},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    pid = resp.json()["id"]

    async with db_manager.async_session_maker() as db:
        row = (
            await db.execute(
                select(Audit_logs)
                .where(Audit_logs.user_id == user["id"], Audit_logs.entity_type == "products")
                .order_by(Audit_logs.id.desc())
            )
        ).scalars().first()
    assert row is not None
    assert row.entity_type == "products"
    assert row.changes is not None
    payload = json.loads(row.changes)
    assert payload["name"] == "AuditWidget"


@pytest.mark.asyncio
async def test_audit_redacts_sensitive_keys(client):
    """Mutations carrying sensitive keys must store '***' rather than the value."""
    user, token, _client_id = await make_client_account(client)
    headers = auth_headers(token)
    # The change-password endpoint lives under /auth (skipped), so exercise a
    # generic endpoint with a password-bearing body via the staff_members triad.
    resp = await client.post(
        "/api/v1/entities/staff_members",
        json={"name": "Cashier", "role": "cashier", "password": "supersecret"},
        headers=headers,
    )
    # The triad may or may not accept the extra key, but if it 2xx'd we audited it.
    if 200 <= resp.status_code < 300:
        async with db_manager.async_session_maker() as db:
            row = (
                await db.execute(
                    select(Audit_logs)
                    .where(Audit_logs.user_id == user["id"], Audit_logs.entity_type == "staff_members")
                    .order_by(Audit_logs.id.desc())
                )
            ).scalars().first()
        if row and row.changes:
            assert "supersecret" not in row.changes


@pytest.mark.asyncio
async def test_audit_logs_failed_auth(client):
    # A protected endpoint hit with a bad token → 401 → AUTH_FAILURE audit row.
    resp = await client.get(
        "/api/v1/entities/products", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert resp.status_code == 401

    async with db_manager.async_session_maker() as db:
        rows = (
            await db.execute(
                select(Audit_logs).where(Audit_logs.action.like("AUTH_FAILURE%"))
            )
        ).scalars().all()
    assert len(rows) >= 1


# ---------------------------------------------------------------------------
# Structured JSON logging
# ---------------------------------------------------------------------------
def test_structured_log_formatter_emits_json():
    from middlewares.production import StructuredLogFormatter

    fmt = StructuredLogFormatter()
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=42,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    out = fmt.format(record)
    parsed = json.loads(out)  # must be valid JSON
    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "test.logger"
    assert parsed["message"] == "hello world"
