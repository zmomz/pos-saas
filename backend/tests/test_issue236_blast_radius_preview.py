"""Issue #236 — master/agent admin actions preview their blast radius.

Two read-only impact endpoints back the confirmation messaging:

* A3 — ``GET /api/v1/packages/{id}/impact`` reports how many agents are still
  provisioned on a package, so archiving (deactivating) an in-use package warns
  with the affected-agents count.
* A4 — ``GET /api/v1/tenant/master/agents/{id}/suspend-impact`` reports the
  suspend cascade (N merchants, M staff) that would be blocked at auth, so the
  master sees the consequence before confirming.

Both are master-only reads; they never mutate, matching the issue's
"underlying suspend-cascade / archival logic (already correct)" out-of-scope.
"""
from conftest import (
    auth_headers,
    make_agent_account,
    make_client_under_agent,
    make_master_account,
)
from core.database import db_manager
from models.agents import Agents
from models.packages import Packages
from models.staff_members import Staff_members


async def _make_package(client_slots: int = 5) -> int:
    async with db_manager.async_session_maker() as db:
        pkg = Packages(
            name="Pro",
            client_slots=client_slots,
            wholesale_price=100,
            suggested_retail_price=150,
            is_active=True,
        )
        db.add(pkg)
        await db.commit()
        await db.refresh(pkg)
        return pkg.id


async def _attach_agent_to_package(agent_id: int, package_id: int) -> None:
    async with db_manager.async_session_maker() as db:
        await db.execute(
            Agents.__table__.update().where(Agents.id == agent_id).values(package_id=package_id)
        )
        await db.commit()


async def _add_staff(owner_user_id: str, status: str = "active") -> None:
    async with db_manager.async_session_maker() as db:
        db.add(Staff_members(
            user_id=owner_user_id,
            name="Cashier",
            role="cashier",
            is_active=status == "active",
            status=status,
        ))
        await db.commit()


# ---------- A3: package archive-with-agents impact ----------

async def test_package_impact_counts_agents_on_package(client):
    _, master_token = await make_master_account(client)
    pkg_id = await _make_package()
    _, _, agent_id = await make_agent_account(client)
    await _attach_agent_to_package(agent_id, pkg_id)

    resp = await client.get(
        f"/api/v1/packages/{pkg_id}/impact", headers=auth_headers(master_token)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["agent_count"] == 1
    assert body["active_agent_count"] == 1


async def test_package_impact_zero_when_unused(client):
    _, master_token = await make_master_account(client)
    pkg_id = await _make_package()

    resp = await client.get(
        f"/api/v1/packages/{pkg_id}/impact", headers=auth_headers(master_token)
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["agent_count"] == 0


async def test_package_impact_requires_master(client):
    _, agent_token, _ = await make_agent_account(client)
    pkg_id = await _make_package()

    resp = await client.get(
        f"/api/v1/packages/{pkg_id}/impact", headers=auth_headers(agent_token)
    )
    assert resp.status_code == 403, resp.text


# ---------- A4: agent suspend cascade preview ----------

async def test_suspend_impact_counts_merchants_and_staff(client):
    _, master_token = await make_master_account(client)
    merchant_user, _, agent_id = await make_agent_account(client)
    m1_user, _, _ = await make_client_under_agent(client, agent_id)
    m2_user, _, _ = await make_client_under_agent(client, agent_id)
    # Two staff under the first merchant; one active, one already terminated.
    await _add_staff(m1_user["id"], status="active")
    await _add_staff(m1_user["id"], status="terminated")

    resp = await client.get(
        f"/api/v1/tenant/master/agents/{agent_id}/suspend-impact",
        headers=auth_headers(master_token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["merchant_count"] == 2
    # Only the still-active staff member would be newly blocked.
    assert body["staff_count"] == 1


async def test_suspend_impact_only_counts_own_merchants(client):
    _, master_token = await make_master_account(client)
    _, _, agent_a = await make_agent_account(client)
    _, _, agent_b = await make_agent_account(client)
    await make_client_under_agent(client, agent_a)
    await make_client_under_agent(client, agent_b)
    await make_client_under_agent(client, agent_b)

    resp = await client.get(
        f"/api/v1/tenant/master/agents/{agent_a}/suspend-impact",
        headers=auth_headers(master_token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["merchant_count"] == 1


async def test_suspend_impact_requires_master(client):
    _, agent_token, agent_id = await make_agent_account(client)

    resp = await client.get(
        f"/api/v1/tenant/master/agents/{agent_id}/suspend-impact",
        headers=auth_headers(agent_token),
    )
    assert resp.status_code == 403, resp.text


async def test_suspend_impact_unknown_agent_404(client):
    _, master_token = await make_master_account(client)

    resp = await client.get(
        "/api/v1/tenant/master/agents/999999/suspend-impact",
        headers=auth_headers(master_token),
    )
    assert resp.status_code == 404, resp.text
