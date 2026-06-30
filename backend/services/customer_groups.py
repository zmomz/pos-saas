"""Customer-groups service (CRM, #221).

Create/list named customer groups and assign a customer to one. Every operation is
owner-scoped by ``user_id`` (SEC-02): a tenant can only see their own groups, and a
customer can only be assigned into a group the same tenant owns. The membership is
stored as ``customers.group_id`` so a customer belongs to at most one group.
"""
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.customer_groups import CustomerGroup
from models.customers import Customers

logger = logging.getLogger(__name__)


class CustomerGroupsService:
    """Service layer for customer groups and membership (#221)."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        *,
        user_id: str,
        client_id: Optional[int],
        name: str,
        tier: Optional[str] = None,
        discount_percent: Optional[float] = None,
    ) -> CustomerGroup:
        """Create a named group for this owner. ``name`` is required and trimmed."""
        group = CustomerGroup(
            user_id=str(user_id),
            client_id=client_id,
            name=name.strip(),
            tier=(tier or "").strip() or None,
            discount_percent=discount_percent,
        )
        self.db.add(group)
        await self.db.commit()
        await self.db.refresh(group)
        logger.info("Created customer group %s for %s", group.id, user_id)
        return group

    async def get_list(self, *, user_id: str) -> list[CustomerGroup]:
        """This owner's groups, newest-first (owner-scoped, SEC-02)."""
        rows = (
            await self.db.execute(
                select(CustomerGroup)
                .where(CustomerGroup.user_id == str(user_id))
                .order_by(CustomerGroup.id.desc())
            )
        ).scalars().all()
        return list(rows)

    async def get_by_id(self, group_id: int, *, user_id: str) -> Optional[CustomerGroup]:
        """A single owned group, or None when out of scope (SEC-02 → router 404)."""
        return (
            await self.db.execute(
                select(CustomerGroup).where(
                    CustomerGroup.id == group_id,
                    CustomerGroup.user_id == str(user_id),
                )
            )
        ).scalar_one_or_none()

    async def assign(
        self, customer_id: int, group_id: Optional[int], *, user_id: str
    ) -> Optional[Customers]:
        """Assign an owned customer to an owned group (or clear with ``group_id=None``).

        Returns the updated customer, or None when the customer — or, when given, the
        group — is not in the caller's scope, so the router 404s (SEC-02)."""
        customer = (
            await self.db.execute(
                select(Customers).where(
                    Customers.id == customer_id,
                    Customers.user_id == str(user_id),
                )
            )
        ).scalar_one_or_none()
        if not customer:
            return None
        if group_id is not None:
            group = await self.get_by_id(group_id, user_id=user_id)
            if not group:
                return None
        customer.group_id = group_id
        await self.db.commit()
        await self.db.refresh(customer)
        logger.info("Assigned customer %s to group %s", customer_id, group_id)
        return customer
