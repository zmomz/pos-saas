from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint


class Staff_branch_access(Base):
    """Per-branch staff access grant (#220 multi-branch: branch permissions).

    A chain's staff member may be scoped to a subset of its branches. Each row
    grants one staff member access to one branch. The rule is permissive-by-
    default so existing single-branch installs are unaffected: a staff member
    with *no* rows here has chain-wide access (every branch); the first grant
    flips them to *scoped* — reachable only at the branches explicitly granted.

    Every row is owner-scoped (SEC-02, ``client_id``/``user_id``) and unique per
    (client_id, staff_id, branch_id) — upserted, never duplicated.
    """

    __tablename__ = "staff_branch_access"
    __table_args__ = (
        UniqueConstraint(
            "client_id", "staff_id", "branch_id", name="uq_staff_branch_access"
        ),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False)
    client_id = Column(Integer, nullable=False)
    staff_id = Column(Integer, nullable=False, index=True)
    branch_id = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
