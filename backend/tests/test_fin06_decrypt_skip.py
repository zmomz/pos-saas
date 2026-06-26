"""FIN-06: distinguish 'no card' from a decrypt failure in the dunning sweep.

A broad ``except Exception`` around ``decrypt_secret`` made a crypto/key error
(an unreadable but *present* card-on-file token) look identical to a genuinely
missing card. The first path is a config/ops fault — the customer DID save a
card; we just can't read it — and must NOT advance dunning toward suspension.
Only a true decline (or a genuinely absent card) advances dunning.

Behaviours:
- a merchant whose card token is present but unreadable -> dunning SKIPPED
  (state untouched) + an operational alert (audit row) is written;
- a merchant with no card token at all -> still advances dunning (a real
  decline), proving the two cases are separated;
- an agent whose quota card token is present but unreadable -> quota dunning
  SKIPPED (not suspended) + an alert.
"""
import pytest
from sqlalchemy import delete, select

from conftest import make_agent_account, register_user, unique_email
from core.database import db_manager
from models.agents import Agents
from models.audit_logs import Audit_logs
from models.clients import Clients


async def _purge_audit(entity_type, entity_id):
    """Drop the audit rows this test minted from the session-shared SQLite.

    The dunning sweep writes its audit rows directly (no SHA-256 chain hash), so
    they would trip ``test_issue019``'s 'every row is chained' assertion if left
    behind in the shared DB. The existing dunning suites avoid this only by
    sorting *after* that test; this file sorts before it, so it cleans up. The
    durable fix is per-test DB isolation (TST-04 / #172)."""
    async with db_manager.async_session_maker() as db:
        await db.execute(
            delete(Audit_logs).where(
                Audit_logs.entity_type == entity_type,
                Audit_logs.entity_id == str(entity_id),
            )
        )
        await db.commit()


async def _make_overdue_client(client, *, agent_id, status="dunning", attempts=2, card_enc=None):
    email = unique_email()
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123", "name": "Merchant"},
    )
    assert resp.status_code == 201, resp.text
    user = resp.json()["user"]
    async with db_manager.async_session_maker() as db:
        merchant = Clients(
            user_id=user["id"],
            agent_id=agent_id,
            business_name="Corner Shop",
            email=email,
            subscription_fee=15.0,
            billing_cycle="monthly",
            subscription_status=status,
            next_billing_date="2000-01-01",
            is_active=True,
            dunning_attempts=attempts,
            invoice_counter=0,
            moyasar_card_token_enc=card_enc,
        )
        db.add(merchant)
        await db.commit()
        await db.refresh(merchant)
        return merchant.id


async def _client_row(client_id):
    async with db_manager.async_session_maker() as db:
        return (await db.execute(select(Clients).where(Clients.id == client_id))).scalar_one()


@pytest.mark.asyncio
async def test_unreadable_card_token_skips_dunning_and_alerts(client, monkeypatch):
    """A present-but-unreadable card token must NOT suspend a paying merchant."""
    _au, _at, a_id = await make_agent_account(client)
    # attempts=2 means one more decline would suspend (default max 3).
    cid = await _make_overdue_client(client, agent_id=a_id, attempts=2, card_enc="ciphertext")

    def _boom(_value):
        raise ValueError("bad key / unreadable ciphertext")

    monkeypatch.setattr("core.crypto.decrypt_secret", _boom)

    from services.dunning import run_client_dunning

    # Drive the dunning step for THIS merchant only (not the global sweep, which
    # would also touch other tests' rows in the session-shared SQLite).
    async with db_manager.async_session_maker() as db:
        merchant = (await db.execute(select(Clients).where(Clients.id == cid))).scalar_one()
        result = await run_client_dunning(db, merchant, actor_user_id="system:test")
        await db.commit()

    # The decrypt failure is NOT a decline: state is untouched, not advanced.
    assert result["action"] == "skipped"
    row = await _client_row(cid)
    assert row.subscription_status == "dunning"   # unchanged, not "suspended"
    assert row.dunning_attempts == 2              # not incremented
    assert row.is_active is True                  # paying customer stays live

    # An operational alert was raised so ops can fix the key.
    async with db_manager.async_session_maker() as db:
        alerts = (
            await db.execute(
                select(Audit_logs).where(
                    Audit_logs.entity_type == "clients",
                    Audit_logs.entity_id == str(cid),
                    Audit_logs.action == "DUNNING_DECRYPT_ERROR",
                )
            )
        ).scalars().all()
    assert len(alerts) == 1
    await _purge_audit("clients", cid)


@pytest.mark.asyncio
async def test_no_card_still_advances_dunning(client, monkeypatch):
    """A genuinely-absent card is a real decline and DOES advance dunning —
    proving 'no card' and 'decrypt failure' are now separated."""
    from services.subscription_billing import SubscriptionChargeError

    _au, _at, a_id = await make_agent_account(client)
    # No card token at all (card_enc=None) -> the charge legitimately fails.
    cid = await _make_overdue_client(client, agent_id=a_id, status="dunning", attempts=2, card_enc=None)

    async def _decline(*args, **kwargs):
        raise SubscriptionChargeError("no card on file")

    monkeypatch.setattr("services.dunning.charge_subscription", _decline)

    from services.dunning import run_client_dunning

    async with db_manager.async_session_maker() as db:
        merchant = (await db.execute(select(Clients).where(Clients.id == cid))).scalar_one()
        result = await run_client_dunning(db, merchant, actor_user_id="system:test")
        await db.commit()

    # This merchant (no card) was charged, declined, and advanced to suspended —
    # not skipped: proves 'no card' and 'decrypt failure' are separated.
    assert result["action"] == "suspended"
    row = await _client_row(cid)
    assert row.subscription_status == "suspended"
    assert row.is_active is False
    await _purge_audit("clients", cid)


@pytest.mark.asyncio
async def test_unreadable_quota_card_skips_quota_dunning(client, monkeypatch):
    """Rail 1: a present-but-unreadable agent quota card must NOT suspend the
    agent (which would cascade his merchants dark) — skip + alert instead."""
    user, _token, _ = await register_user(client)
    async with db_manager.async_session_maker() as db:
        agent = Agents(
            user_id=user["id"],
            company_name="Reseller Co",
            email=unique_email(),
            package_type=10,
            used_slots=0,
            is_active=True,
            quota_price=80.0,
            quota_cycle="monthly",
            quota_status="dunning",
            quota_dunning_attempts=2,  # one more *decline* would suspend
            next_quota_billing_date="2000-01-01",
            quota_card_token_enc="ciphertext",
        )
        db.add(agent)
        await db.commit()
        await db.refresh(agent)
        agent_id = agent.id

    def _boom(_value):
        raise ValueError("bad key / unreadable ciphertext")

    monkeypatch.setattr("core.crypto.decrypt_secret", _boom)

    from services.quota_billing import run_agent_quota_dunning

    async with db_manager.async_session_maker() as db:
        agent = (await db.execute(select(Agents).where(Agents.id == agent_id))).scalar_one()
        result = await run_agent_quota_dunning(db, agent, actor_user_id="system:test")
        await db.commit()
    assert result["action"] == "skipped"

    async with db_manager.async_session_maker() as db:
        agent = (await db.execute(select(Agents).where(Agents.id == agent_id))).scalar_one()
    assert agent.quota_status == "dunning"        # unchanged, NOT suspended
    assert agent.quota_dunning_attempts == 2      # not incremented
    assert agent.is_active is True                # agent + merchants stay live

    async with db_manager.async_session_maker() as db:
        alerts = (
            await db.execute(
                select(Audit_logs).where(
                    Audit_logs.entity_type == "agents",
                    Audit_logs.entity_id == str(agent_id),
                    Audit_logs.action == "QUOTA_DUNNING_DECRYPT_ERROR",
                )
            )
        ).scalars().all()
    assert len(alerts) == 1
    await _purge_audit("agents", agent_id)
