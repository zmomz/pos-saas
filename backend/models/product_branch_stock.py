from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint


class Product_branch_stock(Base):
    """Per-branch stock ledger (Phase 6 multi-branch completeness).

    Client-level ``products.quantity`` is the aggregate/fallback stock. When a
    sale is tagged with a ``branch_id`` the deduction is applied here instead, so
    each branch holds its own quantity and a sale in branch A never touches branch
    B's stock. A row is lazily created (seeded from the product's client-level
    quantity) the first time a branch transacts a product, unless an operator has
    already allocated stock to that branch.
    """

    __tablename__ = "product_branch_stock"
    __table_args__ = (
        UniqueConstraint("client_id", "branch_id", "product_id", name="uq_branch_stock"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False)
    client_id = Column(Integer, nullable=False)
    branch_id = Column(Integer, nullable=False)
    product_id = Column(Integer, nullable=False)
    quantity = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
