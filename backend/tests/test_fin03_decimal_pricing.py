"""FIN-03 — Decimal in promotions, discounts, and gift cards.

Money math in the pricing services must run through ``core.money`` (Decimal,
half-up, a single rounding point) so stacked promotions and gift-card
redemptions are penny-exact and loyalty redemption can never exceed the order
subtotal. These tests pin the three float-drift defects the audit named:

* a percentage promotion rounding a ``*.xx5`` boundary the wrong way
  (``round(2.675, 2) == 2.67`` short-changes the customer a penny);
* summing per-rule float discounts instead of exact 2dp penny amounts;
* a gift-card balance left unredeemable by float subtraction drift
  (``0.30 - 0.10 == 0.19999…`` < ``0.20``);
* a ``+0.01`` slop that let a loyalty redemption exceed the subtotal by a penny.
"""
from decimal import Decimal

import pytest

from conftest import make_client_account
from core.database import db_manager
from models.loyalty_points import Loyalty_points
from models.loyalty_programs import Loyalty_programs
from services.gift_cards import GiftCardsService
from services.loyalty import redeem_points
from services.promotions import CartLine, PromoRule, compute_promotions


def test_percentage_promo_rounds_half_up_penny_exact():
    """50% off a 5.35 line is 2.675 → 2.68 half-up, not 2.67 (float trap) [AC1]."""
    lines = [CartLine(product_id=1, price=5.35, quantity=1)]
    rule = PromoRule(id=1, name="half off", kind="line", disc_type="percentage",
                     value=50.0, product_id=1)

    result = compute_promotions(lines, [rule])

    assert result.total_discount == Decimal("2.68")
    assert result.applied[0].amount == Decimal("2.68")


def test_stacked_promos_sum_penny_exact_amounts():
    """Each promo contributes a real 2dp penny amount; the total is their exact
    sum — not a re-rounded float of rounded-down per-rule values [AC1]."""
    lines = [
        CartLine(product_id=1, price=5.35, quantity=1),
        CartLine(product_id=2, price=5.35, quantity=1),
    ]
    rules = [
        PromoRule(id=1, name="p1", kind="line", disc_type="percentage", value=50.0, product_id=1),
        PromoRule(id=2, name="p2", kind="line", disc_type="percentage", value=50.0, product_id=2),
    ]

    result = compute_promotions(lines, rules)

    assert [a.amount for a in result.applied] == [Decimal("2.68"), Decimal("2.68")]
    assert result.total_discount == Decimal("5.36")


@pytest.mark.asyncio
async def test_gift_card_remaining_balance_redeemable_penny_exact(client):
    """A partial redemption must leave the rest spendable: 0.30 − 0.10 = 0.20,
    redeemable to zero — not 0.19999… that the next 0.20 redemption can't claim."""
    user, _token, client_id = await make_client_account(client)

    async with db_manager.async_session_maker() as db:
        svc = GiftCardsService(db)
        card = await svc.issue(user_id=user["id"], client_id=client_id, amount=0.30)

        assert await svc.redeem(card.id, 0.10, user["id"]) is True
        # The remaining 0.20 must still be claimable to the penny.
        assert await svc.redeem(card.id, 0.20, user["id"]) is True
        await db.commit()

    async with db_manager.async_session_maker() as db:
        refreshed = await GiftCardsService(db).get_by_id(card.id, user["id"])
        assert Decimal(str(refreshed.balance)) == Decimal("0.00")
        assert refreshed.status == "redeemed"


@pytest.mark.asyncio
async def test_loyalty_redemption_capped_at_subtotal_no_penny_slop(client):
    """A redemption worth one penny more than the subtotal is rejected — the
    ``+0.01`` float slop is gone, the cap is exact [AC2]."""
    user, _token, client_id = await make_client_account(client)

    async with db_manager.async_session_maker() as db:
        db.add(Loyalty_points(
            user_id=user["id"], client_id=client_id, customer_id=1,
            points_balance=1000, total_earned=1000, total_redeemed=0,
        ))
        await db.commit()

        program = Loyalty_programs(
            user_id=user["id"], redemption_rate=0.1,
            min_redemption_points=0, is_active=True,
        )
        # 100 points * 0.1 = 10.00 worth, but the order subtotal is only 9.99.
        with pytest.raises(ValueError, match="exceeds order subtotal"):
            await redeem_points(
                db, user_id=user["id"], client_id=client_id, customer_id=1,
                points=100, program=program, max_discount=9.99,
            )
