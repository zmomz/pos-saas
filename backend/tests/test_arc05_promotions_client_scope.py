"""ARC-05 — consistent tenant scoping for the ``promotions`` entity.

``Promotions`` (auto-applied line/category/BOGO rules, ISSUE-058) historically
carried only ``user_id`` while the core tables (products, transactions, …) also
carry ``client_id``. That asymmetry invited cross-tenant query mistakes whenever
code joined or filtered on ``client_id``. This entity is the fourth slice of
ARC-05 (after ``categories``, ``discounts``, and ``discount_codes``): a created
rule now also carries the owning merchant's ``client_id``, stamped on write, so it
isolates consistently with the core tables.

One behaviour per test, exercised through the public HTTP surface.
"""
import uuid

import pytest
from sqlalchemy import select

from core.database import db_manager
from models.promotions import Promotions

from conftest import auth_headers, make_client_account


async def _create_promotion(client, token, **payload):
    payload.setdefault("name", "10% off cola")
    payload.setdefault("kind", "line")
    payload.setdefault("disc_type", "percentage")
    payload.setdefault("value", 10.0)
    payload.setdefault("product_id", 1)
    resp = await client.post(
        "/api/v1/entities/promotions",
        headers=auth_headers(token),
        json=payload,
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_created_promotion_is_stamped_with_owner_client_id(client):
    """A promotion created by a client merchant carries that merchant's client_id."""
    user, token, client_id = await make_client_account(client)

    body = await _create_promotion(client, token)

    assert body["client_id"] == client_id
    # And it is actually persisted, not just echoed back.
    async with db_manager.async_session_maker() as db:
        row = (
            await db.execute(select(Promotions).where(Promotions.id == body["id"]))
        ).scalar_one()
    assert row.client_id == client_id


@pytest.mark.asyncio
async def test_cross_tenant_promotion_list_is_blocked(client):
    """One merchant never sees another merchant's promotion — the ``user_id`` scope
    on the list endpoint keeps the row invisible across tenants."""
    user_a, token_a, client_a = await make_client_account(client)
    user_b, token_b, client_b = await make_client_account(client)

    created = await _create_promotion(client, token_a, name="A-only promo")

    resp = await client.get(
        "/api/v1/entities/promotions", headers=auth_headers(token_b)
    )
    assert resp.status_code == 200, resp.text
    ids = {p["id"] for p in resp.json()["items"]}
    assert created["id"] not in ids


def test_migration_backfills_client_id_from_owning_client(tmp_path):
    """The ARC-05 migration adds ``promotions.client_id`` and backfills it for an
    already-migrated database by matching the row's ``user_id`` to its client."""
    import os

    from sqlalchemy import create_engine, inspect, text

    from alembic import command
    from alembic.config import Config

    ini = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "alembic.ini"
    )
    sync_url = f"sqlite:///{tmp_path / 'arc05_promotions.db'}"
    cfg = Config(ini)
    cfg.set_main_option("sqlalchemy.url", sync_url)

    # Bring the DB up to the revision *before* this one, then seed a legacy
    # promotion whose client_id is unpopulated alongside its owning client.
    command.upgrade(cfg, "e8f9a0b1c2d3")
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
                "INSERT INTO promotions (user_id, name, kind) "
                "VALUES (:uid, 'Legacy promo', 'line')"
            ),
            {"uid": owner_id},
        )

    command.upgrade(cfg, "head")

    insp = inspect(engine)
    assert "client_id" in {c["name"] for c in insp.get_columns("promotions")}
    with engine.connect() as conn:
        backfilled = conn.execute(
            text("SELECT client_id FROM promotions WHERE user_id = :uid"),
            {"uid": owner_id},
        ).scalar_one()
    engine.dispose()
    assert backfilled == client_id
