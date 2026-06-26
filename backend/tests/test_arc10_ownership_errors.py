"""ARC-10 — ownership checks must not swallow DB/infrastructure errors.

``check_ownership`` answers an *authorization* question: does this user own this
record? A missing record (or one owned by another tenant) is a legitimate "no" →
``False``. But a DB/infrastructure error is **not** an authorization answer — the
old code caught every exception and returned ``False``, so a transient DB blip
silently read as "not the owner" (fail-open in the wrong direction, and a swallowed
infra fault). An infra failure must propagate, not be reported as "not owner".
"""
import uuid

import pytest

from core.database import db_manager
from models.discounts import Discounts
from models.loyalty_programs import Loyalty_programs
from services.discounts import DiscountsService
from services.loyalty_programs import Loyalty_programsService


class _BoomSession:
    """A stand-in DB session whose query execution raises an infra error."""

    async def execute(self, *args, **kwargs):
        raise RuntimeError("database is down")


async def _make_discount(user_id: str) -> int:
    async with db_manager.async_session_maker() as db:
        obj = Discounts(user_id=user_id, code=f"C{uuid.uuid4().hex[:8]}", type="percentage", value=10.0)
        db.add(obj)
        await db.commit()
        await db.refresh(obj)
        return obj.id


async def _make_program(user_id: str) -> int:
    async with db_manager.async_session_maker() as db:
        obj = Loyalty_programs(user_id=user_id, name="Gold", is_active=False)
        db.add(obj)
        await db.commit()
        await db.refresh(obj)
        return obj.id


# ---------------------------------------------------------------------------
# Not-owner (or missing) -> False: an honest authorization answer.
# ---------------------------------------------------------------------------
async def test_discounts_check_ownership_false_for_other_user():
    owner = str(uuid.uuid4())
    other = str(uuid.uuid4())
    obj_id = await _make_discount(owner)
    async with db_manager.async_session_maker() as db:
        svc = DiscountsService(db)
        assert await svc.check_ownership(obj_id, owner) is True
        assert await svc.check_ownership(obj_id, other) is False
        assert await svc.check_ownership(10_000_000, owner) is False


async def test_loyalty_programs_check_ownership_false_for_other_user():
    owner = str(uuid.uuid4())
    other = str(uuid.uuid4())
    obj_id = await _make_program(owner)
    async with db_manager.async_session_maker() as db:
        svc = Loyalty_programsService(db)
        assert await svc.check_ownership(obj_id, owner) is True
        assert await svc.check_ownership(obj_id, other) is False
        assert await svc.check_ownership(10_000_000, owner) is False


# ---------------------------------------------------------------------------
# DB/infra error -> propagates (NOT swallowed into a fabricated "not owner").
# ---------------------------------------------------------------------------
async def test_discounts_check_ownership_propagates_db_error():
    svc = DiscountsService(_BoomSession())
    with pytest.raises(RuntimeError):
        await svc.check_ownership(1, "anyone")


async def test_loyalty_programs_check_ownership_propagates_db_error():
    svc = Loyalty_programsService(_BoomSession())
    with pytest.raises(RuntimeError):
        await svc.check_ownership(1, "anyone")
