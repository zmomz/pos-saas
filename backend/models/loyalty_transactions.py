from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String


class Loyalty_transactions(Base):
    """Append-only ledger of loyalty-point movements (ISSUE-028, C4).

    Every change to a customer's ``loyalty_points`` balance that the merchant
    should be able to audit gets a row here: a manual ``adjust`` (``add`` /
    ``deduct``) from the loyalty admin page today, and — when ISSUE-044 lands —
    the sale-driven ``earned`` / ``redeemed`` legs too. The admin "Points
    History" tab reads this table, so a row carries enough to render without a
    join back to the originating sale.
    """

    __tablename__ = "loyalty_transactions"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False, index=True)
    client_id = Column(Integer, nullable=True)
    customer_id = Column(Integer, nullable=False, index=True)
    # "earned" | "redeemed" | "add" | "deduct" — the page colour-codes add/earned
    # as a credit and deduct/redeemed as a debit.
    type = Column(String, nullable=False)
    # Always the positive magnitude of the movement; the sign is implied by type.
    points = Column(Integer, nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
