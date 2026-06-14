from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Float, Integer, String, UniqueConstraint


class Variant_branch_stock(Base):
    """Per-branch stock ledger for a product *variant* (ISSUE-067, INV-03 × INV-04).

    Mirrors :class:`models.product_branch_stock.Product_branch_stock`, but keyed by
    ``variant_id`` instead of ``product_id``. A variant's client-level
    ``product_variants.quantity`` is the aggregate/fallback stock; when a sale is
    tagged with a ``branch_id`` the deduction is applied here instead, so each
    branch holds its own variant quantity and a variant sale in branch A never
    touches branch B's stock. A row is lazily created (seeded from the variant's
    client-level quantity) the first time a branch transacts a variant, unless an
    operator has already allocated stock to that branch.
    """

    __tablename__ = "variant_branch_stock"
    __table_args__ = (
        UniqueConstraint(
            "client_id", "branch_id", "variant_id", name="uq_variant_branch_stock"
        ),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False)
    client_id = Column(Integer, nullable=False)
    branch_id = Column(Integer, nullable=False)
    variant_id = Column(Integer, nullable=False)
    # Float to mirror product_branch_stock and the variant façade quantity.
    quantity = Column(Float, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
