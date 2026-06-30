from core.database import Base
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Integer, String, UniqueConstraint


class Branch_promotion_override(Base):
    """Per-branch opt-out of a chain promotion (#220 multi-branch: branch promotions).

    A chain configures auto-applied promotions once (ISSUE-058); by default every
    active promotion runs at every branch. A branch may opt out of a specific
    promotion (e.g. a clearance promo that should not run at the flagship) by
    carrying a row here with ``is_enabled = False``. Absent a row, the promotion
    runs at the branch. One row per (client_id, branch_id, promotion_id) —
    upserted, never duplicated; re-enabling toggles ``is_enabled`` back on.
    """

    __tablename__ = "branch_promotion_override"
    __table_args__ = (
        UniqueConstraint(
            "client_id", "branch_id", "promotion_id", name="uq_branch_promotion_override"
        ),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False)
    client_id = Column(Integer, nullable=False)
    branch_id = Column(Integer, nullable=False)
    promotion_id = Column(Integer, nullable=False)
    is_enabled = Column(Boolean, nullable=False, default=True, server_default="1")
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
