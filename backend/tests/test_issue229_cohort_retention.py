"""Issue #229 (M9·Analytics) — cohort retention analysis.

The cohort slice of the advanced-analytics epic. Where the CLV/repeat-rate slice
answers "who are our customers and what are they worth" and peak-hours answers
"when do they buy", cohorts answer "how well do we *keep* them": every attributed
customer is grouped by the calendar month of their first purchase (their cohort),
and each cohort is tracked forward month by month to see what fraction come back.

The retention triangle it produces is the raw material for a cohort heatmap. It
reuses the analytics identity + exclusion rules the sibling reports established:

* customers are keyed on ``customer_phone`` (the only stable buyer identity);
* held/voided tickets and credit-note refunds are not selling activity, so they
  neither form a cohort nor count as a return; anonymous (no-phone) sales too;
* offset 0 (the cohort's own month) is 100% retained by construction;
* retention decays as members fail to return in later month offsets;
* one tenant's customers never leak into another's cohorts.
"""
from datetime import datetime, timezone

from conftest import auth_headers, make_client_account
from core.database import db_manager
from models.transactions import Transactions


def _month_start(months_ago):
    """Noon on the 15th of the month ``months_ago`` calendar months before now.

    Day 15 / noon keeps every seeded timestamp comfortably inside its month
    (no month-length or DST edge) and, for ``months_ago >= 1``, safely in the
    past regardless of the day the suite runs.
    """
    now = datetime.now(timezone.utc)
    year, month = now.year, now.month - months_ago
    while month <= 0:
        month += 12
        year -= 1
    return datetime(year, month, 15, 12, 0, tzinfo=timezone.utc)


async def _seed_sale(
    client_id,
    user_id,
    months_ago,
    total,
    *,
    phone,
    name=None,
    status="completed",
    idx=0,
):
    """One transaction attributed to ``phone`` in the month ``months_ago`` back."""
    created = _month_start(months_ago)
    async with db_manager.async_session_maker() as db:
        db.add(
            Transactions(
                user_id=user_id,
                client_id=client_id,
                invoice_number=f"INV-CO-{client_id}-{status}-{months_ago}-{phone}-{idx}",
                subtotal=total,
                vat_amount=0.0,
                discount_amount=0.0,
                total_amount=total,
                payment_method="cash",
                status=status,
                customer_phone=phone,
                customer_name=name,
                created_at=created,
            )
        )
        await db.commit()


def _cells_by_offset(cohort):
    return {c["month_offset"]: c for c in cohort["cells"]}


async def test_single_customer_retained_across_months(client):
    """A customer buying three consecutive months is 100% retained at each offset."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    await _seed_sale(client_id, user["id"], 3, 10.0, phone="0500000001", idx=0)
    await _seed_sale(client_id, user["id"], 2, 20.0, phone="0500000001", idx=1)
    await _seed_sale(client_id, user["id"], 1, 30.0, phone="0500000001", idx=2)

    resp = await client.get("/api/v1/reports/cohorts?lookback=400", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["method"] == "monthly_retention"
    assert body["lookback_days"] == 400
    assert body["total_customers"] == 1
    assert len(body["cohorts"]) == 1

    cohort = body["cohorts"][0]
    assert cohort["cohort_size"] == 1
    cells = _cells_by_offset(cohort)
    for offset in (0, 1, 2):
        assert cells[offset]["active_customers"] == 1
        assert abs(cells[offset]["retention_rate"] - 1.0) < 0.001


async def test_retention_decays_and_late_joiners_form_own_cohort(client):
    """A two-member cohort half-retains at offset 1; a later first-buyer is its own cohort."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    # Cohort M (2 months ago): Alice and Bob both first buy. Only Alice returns
    # the next month → offset-1 retention 1/2. Carol first buys 1 month ago →
    # she seeds her own single-member cohort.
    await _seed_sale(client_id, user["id"], 2, 10.0, phone="0500000001", name="Alice", idx=0)
    await _seed_sale(client_id, user["id"], 2, 10.0, phone="0500000002", name="Bob", idx=0)
    await _seed_sale(client_id, user["id"], 1, 20.0, phone="0500000001", name="Alice", idx=1)
    await _seed_sale(client_id, user["id"], 1, 50.0, phone="0500000003", name="Carol", idx=0)

    resp = await client.get("/api/v1/reports/cohorts?lookback=400", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["total_customers"] == 3
    # Chronological order: the older (2-months-ago) cohort first.
    assert len(body["cohorts"]) == 2
    older, newer = body["cohorts"]

    assert older["cohort_size"] == 2
    older_cells = _cells_by_offset(older)
    assert older_cells[0]["active_customers"] == 2
    assert abs(older_cells[0]["retention_rate"] - 1.0) < 0.001
    assert older_cells[1]["active_customers"] == 1
    assert abs(older_cells[1]["retention_rate"] - 0.5) < 0.001

    assert newer["cohort_size"] == 1
    newer_cells = _cells_by_offset(newer)
    assert newer_cells[0]["active_customers"] == 1
    # Carol never returns → no offset-1 cell for her cohort.
    assert 1 not in newer_cells


async def test_held_voided_credit_note_and_anonymous_excluded(client):
    """Non-selling rows neither form a cohort nor count as a return."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    # Alice's one real purchase 2 months ago is her whole history.
    await _seed_sale(client_id, user["id"], 2, 10.0, phone="0500000001", name="Alice", idx=0)
    # A held, a voided and a credit-note "return" 1 month ago must NOT create an
    # offset-1 retention for Alice.
    await _seed_sale(client_id, user["id"], 1, 99.0, phone="0500000001", status="held", idx=1)
    await _seed_sale(client_id, user["id"], 1, 99.0, phone="0500000001", status="voided", idx=2)
    await _seed_sale(client_id, user["id"], 1, 5.0, phone="0500000001", status="credit_note", idx=3)
    # A phone seen only on a credit note is not a customer / cohort.
    await _seed_sale(client_id, user["id"], 2, 5.0, phone="0500000002", status="credit_note", idx=0)
    # Anonymous walk-ins carry no phone and cannot be attributed to a cohort.
    await _seed_sale(client_id, user["id"], 2, 77.0, phone="", idx=0)
    await _seed_sale(client_id, user["id"], 2, 77.0, phone=None, idx=1)

    resp = await client.get("/api/v1/reports/cohorts?lookback=400", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["total_customers"] == 1
    assert len(body["cohorts"]) == 1
    cohort = body["cohorts"][0]
    assert cohort["cohort_size"] == 1
    cells = _cells_by_offset(cohort)
    assert set(cells) == {0}  # only the cohort's own month, no phantom return


async def test_empty_window_yields_no_cohorts(client):
    """A tenant with no attributable sales gets an empty, well-formed response."""
    user, token, client_id = await make_client_account(client)
    headers = auth_headers(token)

    resp = await client.get("/api/v1/reports/cohorts?lookback=400", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_customers"] == 0
    assert body["cohorts"] == []


async def test_cohorts_are_tenant_scoped(client):
    """One tenant's customers never leak into another tenant's cohorts."""
    user_a, token_a, client_a = await make_client_account(client)
    user_b, token_b, client_b = await make_client_account(client)

    await _seed_sale(client_b, user_b["id"], 2, 500.0, phone="0500009999", idx=0)

    resp = await client.get(
        "/api/v1/reports/cohorts?lookback=400", headers=auth_headers(token_a)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_customers"] == 0
    assert body["cohorts"] == []
