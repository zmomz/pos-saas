"""ARC-05 — consistent tenant scoping for the ``discount_codes`` entity.

``DiscountCodes`` (single-use unique codes, ISSUE-059) historically carried only
``user_id`` while the core tables (products, transactions, …) also carry
``client_id``. That asymmetry invited cross-tenant query mistakes whenever code
joined or filtered on ``client_id``. This entity is the third slice of ARC-05
(after ``categories`` and ``discounts``): minted codes now also carry the owning
merchant's ``client_id``, stamped on write, so they isolate consistently with the
core tables.

One behaviour per test, exercised through the public HTTP surface.
"""
import uuid

import pytest
from sqlalchemy import select

from core.database import db_manager
from models.discount_codes import DiscountCodes

from conftest import auth_headers, make_client_account


async def _generate_codes(client, token, count=2, type="percentage", value=10):
    resp = await client.post(
        "/api/v1/entities/discount-codes/generate",
        headers=auth_headers(token),
        json={"count": count, "type": type, "value": value},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_generated_codes_are_stamped_with_owner_client_id(client):
    """Codes minted by a client merchant carry that merchant's client_id."""
    user, token, client_id = await make_client_account(client)

    body = await _generate_codes(client, token, count=3)

    assert all(c["client_id"] == client_id for c in body["codes"])
    # And it is actually persisted, not just echoed back.
    async with db_manager.async_session_maker() as db:
        rows = (
            await db.execute(
                select(DiscountCodes).where(DiscountCodes.batch_id == body["batch_id"])
            )
        ).scalars().all()
    assert rows and all(r.client_id == client_id for r in rows)


@pytest.mark.asyncio
async def test_cross_tenant_code_redemption_is_blocked(client):
    """One merchant can never redeem another merchant's unique code — the
    ``user_id`` scope on ``get_by_code`` keeps the row invisible across tenants."""
    user_a, token_a, client_a = await make_client_account(client)
    user_b, token_b, client_b = await make_client_account(client)

    minted = await _generate_codes(client, token_a, count=1)
    code = minted["codes"][0]["code"]

    # B tries to redeem A's freshly-minted code — it is not in B's scope.
    resp = await client.post(
        "/api/v1/entities/discount-codes/redeem",
        headers=auth_headers(token_b),
        json={"code": code, "subtotal": 100},
    )
    assert resp.status_code == 400, resp.text
    assert "invalid" in resp.json()["detail"].lower()


def test_migration_backfills_client_id_from_owning_client(tmp_path):
    """The ARC-05 migration adds ``discount_codes.client_id`` and backfills it for
    an already-migrated database by matching the row's ``user_id`` to its client."""
    import os

    from sqlalchemy import create_engine, inspect, text

    from alembic import command
    from alembic.config import Config

    ini = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "alembic.ini"
    )
    sync_url = f"sqlite:///{tmp_path / 'arc05_discount_codes.db'}"
    cfg = Config(ini)
    cfg.set_main_option("sqlalchemy.url", sync_url)

    # Bring the DB up to the revision *before* this one, then seed a legacy code
    # whose client_id is unpopulated alongside its owning client.
    command.upgrade(cfg, "d7e8f9a0b1c2")
    engine = create_engine(sync_url)
    owner_id = "owner-" + uuid.uuid4().hex[:8]
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO users (id, email, role) VALUES (:id, :email, 'user')"),
            {"id": owner_id, "email": f"owner_{uuid.uuid4().hex[:8]}@e.com"},
        )
        conn.execute(
            text(
                "INSERT INTO clients (user_id, agent_id, business_name, email) "
                "VALUES (:uid, 1, 'Shop', :email)"
            ),
            {"uid": owner_id, "email": f"shop_{uuid.uuid4().hex[:8]}@e.com"},
        )
        client_id = conn.execute(
            text("SELECT id FROM clients WHERE user_id = :uid"), {"uid": owner_id}
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO discount_codes (user_id, batch_id, code, type, value, redeemed) "
                "VALUES (:uid, 'legacybatch', 'LEGACYCODE', 'fixed', 5, 0)"
            ),
            {"uid": owner_id},
        )

    command.upgrade(cfg, "head")

    insp = inspect(engine)
    assert "client_id" in {c["name"] for c in insp.get_columns("discount_codes")}
    with engine.connect() as conn:
        backfilled = conn.execute(
            text("SELECT client_id FROM discount_codes WHERE user_id = :uid"),
            {"uid": owner_id},
        ).scalar_one()
    engine.dispose()
    assert backfilled == client_id
