from core.database import Base
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Integer, String, UniqueConstraint


class Branch_catalog_override(Base):
    """Per-branch opt-out of a shared chain product (#220 multi-branch: shared catalog).

    A multi-location chain manages ONE shared product catalog centrally; by default
    every active chain product is available at every branch. A branch may opt a
    product *out* of its local catalog (e.g. an outlet that doesn't carry a premium
    line) by carrying a row here with ``is_available = False``. Absent a row, the
    product is available at the branch. One row per (client_id, branch_id,
    product_id) — upserted, never duplicated; re-stocking toggles ``is_available``
    back on.
    """

    __tablename__ = "branch_catalog_override"
    __table_args__ = (
        UniqueConstraint(
            "client_id", "branch_id", "product_id", name="uq_branch_catalog_override"
        ),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False)
    client_id = Column(Integer, nullable=False)
    branch_id = Column(Integer, nullable=False)
    product_id = Column(Integer, nullable=False)
    is_available = Column(Boolean, nullable=False, default=True, server_default="1")
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
