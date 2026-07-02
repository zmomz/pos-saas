"""M7·Compliance (#270) — scheduled data-retention enforcement (cron sweep).

The per-tenant retention policy (#227) minimizes dormant customer PII, but until
now enforcement only ran when a merchant manually POSTed
``/retention-policy/enforce`` — a set-and-forget policy was never actually
enforced. This slice adds the ``retention.enforce`` background job: a sweep that
iterates every tenant with an *armed* policy (``customer_pii_retention_days`` not
null) and applies the PDPL erasure under a ``system:`` actor, with no human in
the loop.

The sweep is the exact unit of work the worker cron schedules
(``run_job("retention.enforce")``); these tests drive it through the job-queue
seam (memory backend → runs inline) so they pin the *scheduled path* itself:
every armed tenant enforced, unarmed tenants untouched (isolation), a ``system:``
actor on the audit + consent trail, and idempotent re-runs.
"""
from datetime import datetime, timedelta

from sqlalchemy import select, update

from conftest import auth_headers, make_client_account
from core.database import db_manager
from models.audit_logs import Audit_logs
from models.customer_consent_events import CustomerConsentEvent
from models.customers import Customers
from services import job_queue

CUSTOMERS = "/api/v1/entities/customers"
POLICY = f"{CUSTOMERS}/retention-policy"
ERASE_ACTION = "PDPL_RETENTION_ERASE_CUSTOMER"


async def _make_customer(client, token, **fields):
    body = {"name": "Sweep Cust"}
    body.update(fields)
    r = await client.post(CUSTOMERS, json=body, headers=auth_headers(token))
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _arm_policy(client, token, days):
    r = await client.put(
        POLICY, json={"customer_pii_retention_days": days}, headers=auth_headers(token)
    )
    assert r.status_code == 200, r.text


async def _backdate(customer_id, days):
    """Age a customer's ``updated_at`` so it reads as dormant for ``days`` days."""
    old = datetime.now() - timedelta(days=days)
    async with db_manager.async_session_maker() as db:
        await db.execute(
            update(Customers).where(Customers.id == customer_id).values(updated_at=old)
        )
        await db.commit()


async def _customer(customer_id):
    async with db_manager.async_session_maker() as db:
        return (
            await db.execute(select(Customers).where(Customers.id == customer_id))
        ).scalar_one()


async def _erase_audits(customer_id):
    async with db_manager.async_session_maker() as db:
        return (
            await db.execute(
                select(Audit_logs).where(
                    Audit_logs.action == ERASE_ACTION,
                    Audit_logs.entity_id == str(customer_id),
                )
            )
        ).scalars().all()


async def test_sweep_enforces_every_armed_tenant(client):
    """The scheduled sweep minimizes dormant PII for *every* armed tenant with no
    manual /enforce call — the whole point of the cron."""
    _, token_a, _ = await make_client_account(client)
    _, token_b, _ = await make_client_account(client)
    await _arm_policy(client, token_a, 30)
    await _arm_policy(client, token_b, 30)
    cid_a = await _make_customer(client, token_a, phone="0500000001")
    cid_b = await _make_customer(client, token_b, phone="0500000002")
    await _backdate(cid_a, 100)
    await _backdate(cid_b, 100)

    await job_queue.enqueue("retention.enforce")

    a = await _customer(cid_a)
    b = await _customer(cid_b)
    assert a.pii_erased_at is not None and a.phone is None
    assert b.pii_erased_at is not None and b.phone is None


async def test_sweep_skips_tenants_without_an_armed_policy(client):
    """A tenant that never armed a policy is untouched (isolation + opt-in) — the
    sweep only visits tenants with a non-null retention window."""
    _, token, _ = await make_client_account(client)  # never sets a policy
    cid = await _make_customer(client, token, phone="0500000003")
    await _backdate(cid, 9999)

    await job_queue.enqueue("retention.enforce")

    c = await _customer(cid)
    assert c.pii_erased_at is None and c.phone == "0500000003"


async def test_sweep_uses_a_system_actor_and_records_consent_withdrawal(client):
    """Enforcement runs as a ``system:`` actor (no human), and still writes the
    audit + consent-withdrawal trail the manual path writes."""
    _, token, _ = await make_client_account(client)
    await _arm_policy(client, token, 30)
    cid = await _make_customer(
        client, token, phone="0500000004", marketing_consent=True
    )
    await _backdate(cid, 100)

    await job_queue.enqueue("retention.enforce")

    audits = await _erase_audits(cid)
    assert len(audits) == 1
    assert audits[0].user_id.startswith("system:")

    async with db_manager.async_session_maker() as db:
        consents = (
            await db.execute(
                select(CustomerConsentEvent).where(
                    CustomerConsentEvent.customer_id == cid
                )
            )
        ).scalars().all()
    assert any(e.granted is False and e.source == "erase" for e in consents)


async def test_sweep_is_idempotent(client):
    """Re-running the sweep erases nothing already erased (one audit row, not two)."""
    _, token, _ = await make_client_account(client)
    await _arm_policy(client, token, 30)
    cid = await _make_customer(
        client, token, phone="0500000005", marketing_consent=True
    )
    await _backdate(cid, 100)

    await job_queue.enqueue("retention.enforce")
    await job_queue.enqueue("retention.enforce")

    assert len(await _erase_audits(cid)) == 1
