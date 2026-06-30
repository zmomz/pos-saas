"""Campaigns service (CRM, #221).

Create/list marketing campaigns and resolve a campaign's audience. Every operation
is owner-scoped by ``user_id`` (SEC-02): a tenant can only see their own campaigns,
and a campaign can only target a group the same tenant owns. ``create`` returns None
when the target group is foreign/unknown so the router 404s.
"""
import logging
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.campaigns import Campaign
from models.customer_groups import CustomerGroup
from models.customers import Customers

logger = logging.getLogger(__name__)


class CampaignsService:
    """Service layer for marketing campaigns (#221)."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        *,
        user_id: str,
        client_id: Optional[int],
        name: str,
        channel: str = "sms",
        message: Optional[str] = None,
        target_group_id: Optional[int] = None,
    ) -> Optional[Campaign]:
        """Create a campaign for this owner.

        When ``target_group_id`` is set it must name a group the caller owns;
        otherwise returns None so the router 404s (SEC-02)."""
        if target_group_id is not None:
            group = (
                await self.db.execute(
                    select(CustomerGroup).where(
                        CustomerGroup.id == target_group_id,
                        CustomerGroup.user_id == str(user_id),
                    )
                )
            ).scalar_one_or_none()
            if not group:
                return None
        campaign = Campaign(
            user_id=str(user_id),
            client_id=client_id,
            name=name.strip(),
            channel=(channel or "sms").strip() or "sms",
            message=(message or "").strip() or None,
            target_group_id=target_group_id,
            status="draft",
        )
        self.db.add(campaign)
        await self.db.commit()
        await self.db.refresh(campaign)
        logger.info("Created campaign %s for %s", campaign.id, user_id)
        return campaign

    async def get_list(self, *, user_id: str) -> list[Campaign]:
        """This owner's campaigns, newest-first (owner-scoped, SEC-02)."""
        rows = (
            await self.db.execute(
                select(Campaign)
                .where(Campaign.user_id == str(user_id))
                .order_by(Campaign.id.desc())
            )
        ).scalars().all()
        return list(rows)

    async def audience_count(self, campaign: Campaign, *, user_id: str) -> int:
        """How many of the owner's customers this campaign would reach.

        Targeted ⇒ the members of ``target_group_id``; untargeted ⇒ every customer.
        Always scoped to the owner so the count never leaks across tenants."""
        stmt = select(func.count()).select_from(Customers).where(
            Customers.user_id == str(user_id)
        )
        if campaign.target_group_id is not None:
            stmt = stmt.where(Customers.group_id == campaign.target_group_id)
        return int((await self.db.execute(stmt)).scalar_one() or 0)
