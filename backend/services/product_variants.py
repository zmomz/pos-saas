import logging
from typing import Optional, Dict, Any, List

from fastapi import HTTPException
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.product_variants import Product_variants
from services.query_filter import apply_query_filters

# SEC-17: columns a client may filter on via the list endpoint's ?query=.
FILTERABLE_FIELDS = frozenset({"barcode", "client_id", "id", "is_active", "product_id", "sku"})
from models.products import Products

logger = logging.getLogger(__name__)


# ------------------ Service Layer ------------------
class Product_variantsService:
    """Service layer for Product_variants operations (INV-04, F-033).

    Mirrors the generated entity-triad service (``user_id``-scoped ownership
    enforced here, not in the router) so a variant can never be read or mutated
    across tenants (SEC-02).
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: Dict[str, Any], user_id: Optional[str] = None) -> Optional[Product_variants]:
        """Create a new product_variants"""
        try:
            if user_id:
                data['user_id'] = user_id
            obj = Product_variants(**data)
            self.db.add(obj)
            await self.db.commit()
            await self.db.refresh(obj)
            logger.info(f"Created product_variants with id: {obj.id}")
            return obj
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error creating product_variants: {str(e)}")
            raise

    async def check_ownership(self, obj_id: int, user_id: str) -> bool:
        """Check if user owns this record"""
        try:
            obj = await self.get_by_id(obj_id, user_id=user_id)
            return obj is not None
        except Exception as e:
            logger.error(f"Error checking ownership for product_variants {obj_id}: {str(e)}")
            return False

    async def get_by_id(self, obj_id: int, user_id: Optional[str] = None) -> Optional[Product_variants]:
        """Get product_variants by ID (user can only see their own records)"""
        try:
            query = select(Product_variants).where(Product_variants.id == obj_id)
            if user_id:
                query = query.where(Product_variants.user_id == user_id)
            result = await self.db.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching product_variants {obj_id}: {str(e)}")
            raise

    async def get_list(
        self,
        skip: int = 0,
        limit: int = 20,
        user_id: Optional[str] = None,
        query_dict: Optional[Dict[str, Any]] = None,
        sort: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get paginated list of product_variantss (user can only see their own records)"""
        try:
            query = select(Product_variants)
            count_query = select(func.count(Product_variants.id))

            if user_id:
                query = query.where(Product_variants.user_id == user_id)
                count_query = count_query.where(Product_variants.user_id == user_id)

            query, count_query = apply_query_filters(
                Product_variants, query, count_query, query_dict, FILTERABLE_FIELDS
            )

            count_result = await self.db.execute(count_query)
            total = count_result.scalar()

            if sort:
                if sort.startswith('-'):
                    field_name = sort[1:]
                    if hasattr(Product_variants, field_name):
                        query = query.order_by(getattr(Product_variants, field_name).desc())
                else:
                    if hasattr(Product_variants, sort):
                        query = query.order_by(getattr(Product_variants, sort))
            else:
                query = query.order_by(Product_variants.id.desc())

            result = await self.db.execute(query.offset(skip).limit(limit))
            items = result.scalars().all()

            return {
                "items": items,
                "total": total,
                "skip": skip,
                "limit": limit,
            }
        except Exception as e:
            logger.error(f"Error fetching product_variants list: {str(e)}")
            raise

    async def update(self, obj_id: int, update_data: Dict[str, Any], user_id: Optional[str] = None) -> Optional[Product_variants]:
        """Update product_variants (requires ownership)"""
        try:
            obj = await self.get_by_id(obj_id, user_id=user_id)
            if not obj:
                logger.warning(f"Product_variants {obj_id} not found for update")
                return None
            for key, value in update_data.items():
                if hasattr(obj, key) and key != 'user_id':
                    setattr(obj, key, value)

            await self.db.commit()
            await self.db.refresh(obj)
            logger.info(f"Updated product_variants {obj_id}")
            return obj
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating product_variants {obj_id}: {str(e)}")
            raise

    async def delete(self, obj_id: int, user_id: Optional[str] = None) -> bool:
        """Delete product_variants (requires ownership)"""
        try:
            obj = await self.get_by_id(obj_id, user_id=user_id)
            if not obj:
                logger.warning(f"Product_variants {obj_id} not found for deletion")
                return False
            await self.db.delete(obj)
            await self.db.commit()
            logger.info(f"Deleted product_variants {obj_id}")
            return True
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error deleting product_variants {obj_id}: {str(e)}")
            raise


# ------------------ POS sale-path helpers ------------------
# These operate within the caller's DB session and do NOT commit — the POS sale
# path commits the variant-stock movements atomically with the sale, exactly like
# the client-level ``routers.pos._deduct_inventory`` and the branch ledger.

def _variant_lines(items: List) -> Dict[int, float]:
    """Aggregate requested quantities per variant_id across cart lines.

    Accepts either Pydantic cart items (``.variant_id`` / ``.quantity``) or plain
    dicts (a refunded/voided ``items_json`` line). Lines with no ``variant_id`` are
    ignored — they decrement product/branch stock on the normal path.
    """
    requested: Dict[int, float] = {}
    for item in items:
        if isinstance(item, dict):
            vid = item.get("variant_id")
            qty = item.get("quantity") or 0
        else:
            vid = getattr(item, "variant_id", None)
            qty = getattr(item, "quantity", 0) or 0
        if not vid:
            continue
        requested[int(vid)] = requested.get(int(vid), 0.0) + float(qty)
    return requested


async def deduct_variant_inventory(
    db: AsyncSession,
    client_id: int,
    items: List,
    allow_negative_stock: bool,
) -> None:
    """Decrement per-variant stock for any sold variant lines (no commit).

    Raises ``HTTPException(400)`` on insufficient variant stock unless overselling
    is allowed. A variant_id that does not map to one of this client's variants is
    skipped (treated like an ad-hoc line), so a stale/foreign variant can never
    deduct another tenant's stock (SEC-02).
    """
    for variant_id, qty in _variant_lines(items).items():
        variant = (
            await db.execute(
                select(Product_variants).where(
                    Product_variants.id == variant_id,
                    Product_variants.client_id == client_id,
                )
            )
        ).scalar_one_or_none()
        if not variant:
            continue

        # variant stock is an integer SKU count — deduct whole units.
        units = int(qty)

        # DAT-03: decrement with one conditional UPDATE on the variant row (mirrors
        # DAT-01 on Products and DAT-02 on the branch ledger). The ``quantity >= units``
        # guard (dropped when overselling is allowed) makes the check-and-decrement a
        # single atomic statement, so N concurrent variant sales on stock=K let exactly
        # K succeed — no read-check-write oversell race. COALESCE treats a NULL on-hand
        # as 0, and the ``client_id`` predicate keeps cross-tenant isolation (SEC-02).
        stmt = (
            update(Product_variants)
            .where(
                Product_variants.id == variant_id,
                Product_variants.client_id == client_id,
            )
            .values(quantity=func.coalesce(Product_variants.quantity, 0) - units)
        )
        if not allow_negative_stock:
            stmt = stmt.where(func.coalesce(Product_variants.quantity, 0) >= units)

        result = await db.execute(stmt)
        if result.rowcount:
            continue

        # No row updated (and the variant exists): not enough variant stock.
        available = variant.quantity or 0
        raise HTTPException(
            status_code=400,
            detail=(
                f"Insufficient stock for variant '{variant.name}': "
                f"requested {units}, available {available}"
            ),
        )


async def restore_variant_inventory(db: AsyncSession, client_id: int, items: List) -> None:
    """Add quantities back to per-variant stock (inverse of the deduction; no commit)."""
    for variant_id, qty in _variant_lines(items).items():
        await db.execute(
            update(Product_variants)
            .where(
                Product_variants.id == variant_id,
                Product_variants.client_id == client_id,
            )
            .values(quantity=Product_variants.quantity + int(qty))
        )


async def resolve_variant_barcode(
    db: AsyncSession, user_id: str, barcode: str
) -> Optional[Product_variants]:
    """Resolve a scanned barcode to one of the caller's active variants (SEC-02)."""
    code = (barcode or "").strip()
    if not code:
        return None
    return (
        await db.execute(
            select(Product_variants)
            .where(
                Product_variants.user_id == user_id,
                Product_variants.barcode == code,
                Product_variants.is_active.is_(True),
            )
            .order_by(Product_variants.id.asc())
        )
    ).scalars().first()


async def resolve_product_barcode(
    db: AsyncSession, user_id: str, barcode: str
) -> Optional[Products]:
    """Resolve a scanned barcode to one of the caller's products (SEC-02)."""
    code = (barcode or "").strip()
    if not code:
        return None
    return (
        await db.execute(
            select(Products)
            .where(
                Products.user_id == user_id,
                Products.barcode == code,
            )
            .order_by(Products.id.asc())
        )
    ).scalars().first()
