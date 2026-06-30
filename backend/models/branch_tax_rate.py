from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Float, Integer, String, UniqueConstraint


class Branch_tax_rate(Base):
    """Per-branch VAT rate override (#220 multi-branch: branch-level tax).

    A chain applies a default VAT rate — the master's global rate (MA-05), else
    the statutory KSA 15 %. A branch may carry its own rate (e.g. a duty-free
    airport branch at a reduced rate). A row here overrides the chain-wide
    effective rate for exactly one branch; absent a row, the chain rate applies.
    One row per (client_id, branch_id) — upserted, never duplicated.
    """

    __tablename__ = "branch_tax_rate"
    __table_args__ = (
        UniqueConstraint("client_id", "branch_id", name="uq_branch_tax_rate"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False)
    client_id = Column(Integer, nullable=False)
    branch_id = Column(Integer, nullable=False)
    vat_rate = Column(Float, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
