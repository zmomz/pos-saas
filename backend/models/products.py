from core.database import Base
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String


class Products(Base):
    __tablename__ = "products"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False)
    client_id = Column(Integer, nullable=False)
    name = Column(String, nullable=False)
    name_ar = Column(String, nullable=True)
    barcode = Column(String, nullable=True)
    price = Column(Float, nullable=False)
    cost_price = Column(Float, nullable=True)
    # POS-11 (F-011): on-hand stock is a Float so weighted products (sold by
    # fractional weight, e.g. 0.45 kg) track real fractional quantities. Existing
    # integer values remain valid; comparisons/arithmetic are unaffected.
    quantity = Column(Float, nullable=True, default=0, server_default='0')
    # INV-08 (F-035): per-product reorder point. When on-hand <= reorder_point
    # (and reorder_point > 0) the product is flagged low / suggested for a PO.
    # reorder_quantity is the order amount the auto-PO suggestion proposes.
    reorder_point = Column(Integer, nullable=True, default=0, server_default='0')
    reorder_quantity = Column(Integer, nullable=True, default=0, server_default='0')
    # ISSUE-223 (M4 Product): ``brand`` is the marketing name a shopper recognises
    # (e.g. "Panadol"); ``manufacturer`` is the legal maker, which differs from the
    # brand in pharmacy/electronics verticals (e.g. brand "Panadol" / maker "GSK").
    # Both are optional free-text — NULL means "unspecified".
    brand = Column(String, nullable=True)
    manufacturer = Column(String, nullable=True)
    category = Column(String, nullable=True)
    # H7 (ISSUE-038): link a product to the merchant's category tree. The legacy
    # free-text ``category`` above is kept (denormalised) for display continuity;
    # ``category_id`` is the real owner-scoped FK that lists/filters resolve against.
    category_id = Column(Integer, nullable=True)
    vat_rate = Column(Float, nullable=True, default=15.0, server_default='15.0')
    is_active = Column(Boolean, nullable=True, default=True, server_default='true')
    # POS-11 (F-011): weighted & open-price configuration.
    # ``is_weighted`` — the product is sold by weight; the POS captures a fractional
    #   quantity at sale time (manual entry or scale) instead of a unit count, and
    #   ``unit_label`` (e.g. "kg", "g") labels the measure on screen/receipt.
    # ``is_open_price`` — the price is entered at sale time (the catalog ``price`` is
    #   a default/zero), so a sale-time price is expected and is NOT treated as a
    #   fraud-sensitive ``pos.price_override`` (POS-08) of a fixed-price product.
    is_weighted = Column(Boolean, nullable=True, default=False, server_default='false')
    is_open_price = Column(Boolean, nullable=True, default=False, server_default='false')
    unit_label = Column(String, nullable=True)
    # ISSUE-065 (P2 catalog): served URL of the product image (catalog + POS tile
    # grid). The file is stored under ``uploads/products/`` and served from
    # ``/uploads``; NULL means "no image" (the tile falls back to its initial).
    image_url = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)