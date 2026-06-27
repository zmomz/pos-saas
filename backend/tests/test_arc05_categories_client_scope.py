"""ARC-05 — consistent tenant scoping for the ``categories`` entity.

``Categories`` historically carried only ``user_id`` while the core tables
(products, transactions, …) also carry ``client_id``. That asymmetry invited
cross-tenant query mistakes whenever code joined or filtered on ``client_id``.
This entity is the first slice of ARC-05: ``categories`` now also carries the
owning merchant's ``client_id``, stamped on write and honoured as a scoping
filter, so it isolates consistently with the core tables.

One behaviour per test, exercised through the public HTTP surface.
"""
import uuid

import pytest
from sqlalchemy import select, text

from core.database import db_manager
from models.categories import Categories

from conftest import auth_headers, make_client_account


async def _create_category(client, token, name="Beverages"):
    resp = await client.post(
        "/api/v1/entities/categories",
        headers=auth_headers(token),
        json={"name": name},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_created_category_is_stamped_with_owner_client_id(client):
    """A category created by a client merchant carries that merchant's client_id."""
    user, token, client_id = await make_client_account(client)

    body = await _create_category(client, token)

    assert body["client_id"] == client_id
    # And it is actually persisted, not just echoed back.
    async with db_manager.async_session_maker() as db:
        row = (
            await db.execute(select(Categories).where(Categories.id == body["id"]))
        ).scalar_one()
    assert row.client_id == client_id


@pytest.mark.asyncio
async def test_list_is_routed_by_client_id_filter(client):
    """``?query={"client_id": N}`` is honoured: a filter on a *foreign* client id
    returns nothing rather than silently falling back to the caller's own rows."""
    user, token, client_id = await make_client_account(client)
    await _create_category(client, token, name="Bakery")

    foreign_client_id = client_id + 9999

    own = await client.get(
        "/api/v1/entities/categories",
        headers=auth_headers(token),
        params={"query": '{"client_id": %d}' % client_id},
    )
    assert own.status_code == 200, own.text
    assert own.json()["total"] == 1

    foreign = await client.get(
        "/api/v1/entities/categories",
        headers=auth_headers(token),
        params={"query": '{"client_id": %d}' % foreign_client_id},
    )
    assert foreign.status_code == 200, foreign.text
    assert foreign.json()["total"] == 0


@pytest.mark.asyncio
async def test_cross_tenant_category_read_is_blocked(client):
    """One merchant can never read another merchant's category — not via list,
    not via direct id, and not by filtering on the other's client_id."""
    user_a, token_a, client_a = await make_client_account(client)
    user_b, token_b, client_b = await make_client_account(client)

    cat_a = await _create_category(client, token_a, name="Tenant A only")

    # B's list shows none of A's rows.
    listed = await client.get(
        "/api/v1/entities/categories", headers=auth_headers(token_b)
    )
    assert listed.status_code == 200, listed.text
    assert all(item["id"] != cat_a["id"] for item in listed.json()["items"])

    # B cannot fetch A's category by id.
    direct = await client.get(
        f"/api/v1/entities/categories/{cat_a['id']}", headers=auth_headers(token_b)
    )
    assert direct.status_code == 404

    # B cannot smuggle a read by filtering on A's client_id — the user_id scope
    # still wins, so the foreign filter just returns empty.
    smuggle = await client.get(
        "/api/v1/entities/categories",
        headers=auth_headers(token_b),
        params={"query": '{"client_id": %d}' % client_a},
    )
    assert smuggle.status_code == 200, smuggle.text
    assert smuggle.json()["total"] == 0


def test_migration_backfills_client_id_from_owning_client(tmp_path):
    """The ARC-05 migration adds ``categories.client_id`` and backfills it for an
    already-migrated database by matching the row's ``user_id`` to its client."""
    import os

    from sqlalchemy import create_engine, inspect, text

    from alembic import command
    from alembic.config import Config

    ini = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "alembic.ini"
    )
    sync_url = f"sqlite:///{tmp_path / 'arc05.db'}"
    cfg = Config(ini)
    cfg.set_main_option("sqlalchemy.url", sync_url)

    # Bring the DB up to the revision *before* ARC-05, then seed a legacy
    # category whose client_id is unpopulated alongside its owning client.
    command.upgrade(cfg, "a2d3e4f5b6c7")
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
            text("INSERT INTO categories (user_id, name) VALUES (:uid, 'Legacy')"),
            {"uid": owner_id},
        )

    command.upgrade(cfg, "head")

    insp = inspect(engine)
    assert "client_id" in {c["name"] for c in insp.get_columns("categories")}
    with engine.connect() as conn:
        backfilled = conn.execute(
            text("SELECT client_id FROM categories WHERE user_id = :uid"),
            {"uid": owner_id},
        ).scalar_one()
    engine.dispose()
    assert backfilled == client_id
