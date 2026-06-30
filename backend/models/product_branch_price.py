from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Float, Integer, String, UniqueConstraint


class Product_branch_price(Base):
    """Per-branch price override (#220 multi-branch: branch-level pricing).

    The product's client-level ``products.price`` is the chain-wide default. A
    branch may carry its own price for a product (e.g. an airport branch prices a
    bottle of water higher than the suburban one). A row here overrides the base
    price for exactly one (branch, product); absent a row, the base price applies.
    One row per (client_id, branch_id, product_id) — upserted, never duplicated.
    """

    __tablename__ = "product_branch_price"
    __table_args__ = (
        UniqueConstraint("client_id", "branch_id", "product_id", name="uq_branch_price"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False)
    client_id = Column(Integer, nullable=False)
    branch_id = Column(Integer, nullable=False)
    product_id = Column(Integer, nullable=False)
    price = Column(Float, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
