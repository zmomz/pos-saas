"""ISSUE-187 — remaining float money paths routed through ``core/money.py``.

Three money paths still computed in IEEE-754 float and rounded half-even, so a
value landing exactly on a ``.xx5`` boundary drifted a penny the wrong way (the
classic ``round(2.675, 2) == 2.67`` trap). These tests pin each site to exact
Decimal half-up arithmetic — the same rule the customer-facing till uses
everywhere else (FIN-01).
"""
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest


# ---------------------------------------------------------------------------
# 1. POS discount — compute_discount_amount.
# ---------------------------------------------------------------------------
def test_pos_percentage_discount_rounds_half_up_at_boundary():
    from services.discounts import compute_discount_amount

    # 5% of 53.50 = 2.675 -> half-up 2.68 (float half-even gave 2.67).
    discount = SimpleNamespace(type="percentage", value=5)
    amount = compute_discount_amount(discount, Decimal("53.50"))
    assert amount == Decimal("2.68")
    assert isinstance(amount, Decimal)


def test_pos_discount_clamped_to_subtotal_in_decimal():
    from services.discounts import compute_discount_amount

    # A flat discount larger than the order can never push it negative.
    discount = SimpleNamespace(type="fixed", value=80)
    amount = compute_discount_amount(discount, Decimal("50.00"))
    assert amount == Decimal("50.00")
    assert isinstance(amount, Decimal)


# ---------------------------------------------------------------------------
# 2. Subscription coupon / proration.
# ---------------------------------------------------------------------------
def test_apply_coupon_rounds_half_up_at_boundary():
    from services.subscription_billing import apply_coupon

    # 73.25% off 10.00 -> net 2.675 -> half-up 2.68 (float half-even gave 2.67).
    net = apply_coupon(10.0, "percentage", 73.25)
    assert net == Decimal("2.68")
    assert isinstance(net, Decimal)


def test_compute_proration_rounds_half_up_at_boundary():
    from services.subscription_billing import compute_proration

    # (5.35 - 0) * 15/30 = 2.675 -> half-up 2.68 (float half-even gave 2.67).
    amount = compute_proration(0.0, 5.35, 15, 30)
    assert amount == Decimal("2.68")
    assert isinstance(amount, Decimal)


# ---------------------------------------------------------------------------
# 3. Gateway minor units — to_halalas at the boundary.
# ---------------------------------------------------------------------------
class _FakeResp:
    status_code = 200
    content = b"{}"

    def json(self):
        return {
            "id": "pay_187",
            "status": "paid",
            "source": {"company": "mada"},
        }

    def raise_for_status(self):
        return None


class _CapturingClient:
    captured: dict = {}

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None, auth=None):
        _CapturingClient.captured = {"url": url, "json": json}
        return _FakeResp()


@pytest.mark.asyncio
async def test_moyasar_charge_amount_is_penny_exact(monkeypatch):
    """A ``.xx5`` riyal amount converts to halalas penny-exact, not float-drifted.

    ``int(round(2.675 * 100))`` == 267 because ``2.675 * 100`` is ``267.4999…``
    in float; ``to_halalas`` quantizes half-up to 2.68 first -> 268 halalas.
    """
    from services.payment_gateway import MoyasarGateway

    monkeypatch.setattr(httpx, "AsyncClient", _CapturingClient)
    _CapturingClient.captured = {}

    gateway = MoyasarGateway("sk_test_187")
    result = await gateway.charge(
        amount=2.675, tender_type="card", token="tok_card_on_file"
    )

    assert result.approved is True
    assert _CapturingClient.captured["json"]["amount"] == 268
