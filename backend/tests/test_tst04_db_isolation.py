"""TST-04 — per-test database isolation.

The suite shares one session-scoped SQLite file (see conftest ``_init_db``), so
without a reset between tests every row a test inserts leaks into the next one.
A test that asserts a **global** count of some table is therefore order-dependent:
it sees its own rows plus every row any earlier test created.

These two tests each insert a *different* number of ``Agents`` rows and assert
the GLOBAL count equals exactly what they inserted. They only both pass when a
per-test reset fixture wipes the tables between tests (TST-04). Run together
without isolation, whichever executes second fails on the leftover rows.
"""
import uuid

from sqlalchemy import func, select

from core.database import db_manager
from models.agents import Agents


async def _insert_agents(n: int) -> None:
    async with db_manager.async_session_maker() as db:
        for _ in range(n):
            db.add(
                Agents(
                    user_id=str(uuid.uuid4()),
                    company_name="Iso Co",
                    email=f"iso_{uuid.uuid4().hex[:12]}@example.com",
                    package_type=1,
                    used_slots=0,
                    is_active=True,
                )
            )
        await db.commit()


async def _count_agents() -> int:
    async with db_manager.async_session_maker() as db:
        result = await db.execute(select(func.count()).select_from(Agents))
        return result.scalar_one()


async def test_global_agent_count_isolated_a():
    await _insert_agents(2)
    assert await _count_agents() == 2


async def test_global_agent_count_isolated_b():
    await _insert_agents(3)
    assert await _count_agents() == 3
