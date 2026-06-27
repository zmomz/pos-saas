"""SEC-17 — client-driven ``query_dict`` column filtering is allowlist-bound.

List endpoints accept a client JSON ``query`` that the service applied as
``Model.<field> == value`` for *any* column the model happened to have
(``hasattr(Model, field)``). That exposed an unbounded filter surface: a client
could filter on a sensitive column (e.g. a webhook ``secret_key``) and use
equality as a boolean oracle, or filter on internal columns never meant to be
queryable.

Each service now declares an explicit allowlist (``FILTERABLE_FIELDS``) and runs
client filters through the shared :func:`services.query_filter.apply_query_filters`
helper, which applies only allowlisted columns and silently ignores the rest.

These tests pin the behaviour through the service layer (the public interface
the routers call) plus a repo-wide guard that no service re-inlines the raw
``hasattr`` loop.
"""
import pathlib

import pytest

from core.database import db_manager
from models.webhooks import Webhooks
from models.product_variants import Product_variants
from services.webhooks import WebhooksService
from services.product_variants import Product_variantsService

SERVICES_DIR = pathlib.Path(__file__).resolve().parent.parent / "services"


async def _add(*objs):
    async with db_manager.async_session_maker() as db:
        for o in objs:
            db.add(o)
        await db.commit()


@pytest.mark.asyncio
async def test_secret_key_is_not_a_filterable_oracle():
    """A disallowed sensitive column (webhook secret_key) must not filter rows.

    Two webhooks with distinct secrets exist for one user; a query filtering by
    one secret must return BOTH rows (filter ignored), so equality cannot be
    used as a brute-force oracle to confirm a secret value.
    """
    uid = "sec17-user-a"
    await _add(
        Webhooks(user_id=uid, name="wh1", url="https://e1", events="sale", secret_key="topsecret-AAA"),
        Webhooks(user_id=uid, name="wh2", url="https://e2", events="sale", secret_key="topsecret-BBB"),
    )

    async with db_manager.async_session_maker() as db:
        result = await WebhooksService(db).get_list(
            user_id=uid, query_dict={"secret_key": "topsecret-AAA"}
        )

    assert result["total"] == 2
    assert {w.name for w in result["items"]} == {"wh1", "wh2"}


@pytest.mark.asyncio
async def test_allowed_field_still_filters():
    """An allowlisted column (product_variants.product_id) keeps filtering.

    This is the one non-empty filter the SPA actually sends, so the allowlist
    must continue to honour it.
    """
    uid = "sec17-user-b"
    await _add(
        Product_variants(user_id=uid, product_id=10, name="v-ten"),
        Product_variants(user_id=uid, product_id=20, name="v-twenty"),
    )

    async with db_manager.async_session_maker() as db:
        result = await Product_variantsService(db).get_list(
            user_id=uid, query_dict={"product_id": 10}
        )

    assert result["total"] == 1
    assert result["items"][0].name == "v-ten"


@pytest.mark.asyncio
async def test_disallowed_field_on_allowlisted_model_is_ignored():
    """A non-allowlisted column (product_variants.cost_price) does not filter."""
    uid = "sec17-user-c"
    await _add(
        Product_variants(user_id=uid, product_id=1, name="cheap", cost_price=1.0),
        Product_variants(user_id=uid, product_id=2, name="dear", cost_price=99.0),
    )

    async with db_manager.async_session_maker() as db:
        result = await Product_variantsService(db).get_list(
            user_id=uid, query_dict={"cost_price": 1.0}
        )

    assert result["total"] == 2


def test_no_service_inlines_the_query_dict_filter_loop():
    """Repo guard: no service re-implements the raw allowlist-free filter loop.

    Every service must funnel client filters through apply_query_filters, so the
    vulnerable ``for field, value in query_dict.items()`` loop must not reappear
    in any service module.
    """
    offenders = [
        p.name
        for p in SERVICES_DIR.glob("*.py")
        # query_filter.py is the single sanctioned chokepoint that owns the loop.
        if p.name != "query_filter.py"
        and "for field, value in query_dict.items()" in p.read_text(encoding="utf-8")
    ]
    assert offenders == [], f"services still inline the query_dict filter loop: {offenders}"
