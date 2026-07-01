"""M7·Compliance (#227) — regulatory audit export.

Scope item: "Regulatory audit export; ... surface reconcile status." Enterprise
procurement (and a regulator) needs a self-describing, independently verifiable
artifact of the tenant's audit trail — not the UI read-projection the AuditLog
page renders, but the raw compliance rows including the tamper-evidence hash
chain (``prev_hash`` -> ``row_hash``) so an external auditor can re-walk it.

The export is owner-scoped (SEC-02): one tenant's artifact contains only that
tenant's rows. It surfaces the store's *reconcile status* (the outcome of
``verify_audit_chain``) so the artifact itself attests whether the trail is
intact or has been tampered with.
"""
from sqlalchemy import select, update

from conftest import auth_headers, make_client_account
from core.database import db_manager
from models.audit_logs import Audit_logs

CUSTOMERS = "/api/v1/entities/customers"
EXPORT = "/api/v1/entities/audit_logs/regulatory-export"


async def _make_customer(client, token, name="Reg Cust"):
    r = await client.post(CUSTOMERS, json={"name": name}, headers=auth_headers(token))
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def test_export_produces_compliant_artifact(client):
    # AC: a mutation leaves an audited row; the export is a self-describing
    # artifact carrying the raw compliance rows plus their hash-chain fields.
    _, token, _ = await make_client_account(client)
    await _make_customer(client, token)

    r = await client.get(EXPORT, headers=auth_headers(token))
    assert r.status_code == 200, r.text
    art = r.json()

    assert art["artifact_type"] == "regulatory_audit_export"
    assert art.get("format_version")
    assert art.get("generated_at")
    assert art["record_count"] >= 1
    assert len(art["records"]) == art["record_count"]

    rec = art["records"][0]
    # Raw compliance content + tamper-evidence chain (so it is re-verifiable).
    for key in ("id", "action", "created_at", "prev_hash", "row_hash"):
        assert key in rec, (key, rec)
    assert any("customers" in (rr["action"] or "") for rr in art["records"])


async def test_export_surfaces_verified_reconcile_status(client):
    # AC: the artifact surfaces the reconcile status — an untampered store reports
    # verified=True and a non-zero checked count.
    _, token, _ = await make_client_account(client)
    await _make_customer(client, token)

    r = await client.get(EXPORT, headers=auth_headers(token))
    assert r.status_code == 200, r.text
    integrity = r.json()["integrity"]
    assert integrity["verified"] is True
    assert integrity["checked"] >= 1
    assert integrity["broken_id"] is None


async def test_export_reports_tampering_in_reconcile_status(client):
    # AC: if a stored row's content is mutated in place, the export's reconcile
    # status reports the trail as no longer verified (the whole point of it).
    _, token, _ = await make_client_account(client)
    await _make_customer(client, token)

    async with db_manager.async_session_maker() as db:
        target = (
            await db.execute(select(Audit_logs).order_by(Audit_logs.id.asc()).limit(1))
        ).scalar_one()
        await db.execute(
            update(Audit_logs)
            .where(Audit_logs.id == target.id)
            .values(action="TAMPERED")
        )
        await db.commit()

    r = await client.get(EXPORT, headers=auth_headers(token))
    assert r.status_code == 200, r.text
    integrity = r.json()["integrity"]
    assert integrity["verified"] is False
    assert integrity["broken_id"] == target.id
    assert integrity["reason"] == "content_tampered"


async def test_export_is_owner_scoped(client):
    # SEC-02: a tenant's export contains only its own rows, never another
    # tenant's audit activity.
    user_a, token_a, _ = await make_client_account(client)
    user_b, token_b, _ = await make_client_account(client)
    await _make_customer(client, token_a, name="A cust")
    await _make_customer(client, token_b, name="B cust")

    r = await client.get(EXPORT, headers=auth_headers(token_a))
    assert r.status_code == 200, r.text
    owners = {rec["owner_user_id"] for rec in r.json()["records"]}
    assert owners == {str(user_a["id"])}, owners
