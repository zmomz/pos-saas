from core.database import Base
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String


class Product_variants(Base):
    """A sellable variant of a parent product (INV-04, F-033).

    Each variant is its own SKU — its own ``barcode``, ``price`` and ``quantity``
    (stock) — so a "T-Shirt" product can expose "Red / Large" and "Blue / Small"
    as independently-scannable, independently-stocked lines. The POS resolves a
    scanned variant barcode to the variant and decrements *its* stock, leaving
    sibling variants untouched.

    ``attributes`` is a small JSON string of the option axes (e.g.
    ``{"size": "L", "color": "Red"}``); ``name`` is the human label shown on the
    line. Stock is tracked at the variant level (client-scoped) — per-branch
    variant ledgers (INV-03 × INV-04) are a deeper follow-on and not modeled here.
    """

    __tablename__ = "product_variants"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False, index=True)
    client_id = Column(Integer, nullable=True, index=True)
    product_id = Column(Integer, nullable=False, index=True)
    name = Column(String, nullable=False)
    attributes = Column(String, nullable=True)
    sku = Column(String, nullable=True)
    barcode = Column(String, nullable=True)
    price = Column(Float, nullable=True)
    cost_price = Column(Float, nullable=True)
    quantity = Column(Integer, nullable=True, default=0, server_default='0')
    is_active = Column(Boolean, nullable=True, default=True, server_default='true')
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
