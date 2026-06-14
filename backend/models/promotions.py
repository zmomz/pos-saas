from core.database import Base
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String


class Promotions(Base):
    """An auto-applied promotion rule (ISSUE-058, P2 pricing).

    Unlike a coded ``Discounts`` row (entered by code, priced against the whole
    order), a promotion targets *part* of the cart and *fires on its own* when the
    cart meets ``min_subtotal``. ``kind`` selects the matcher/pricer:

    * ``line``     — discount ``product_id`` by ``value`` as ``disc_type``;
    * ``category`` — discount every line whose ``category`` matches;
    * ``bogo``     — buy ``bogo_buy_qty`` of ``product_id`` get ``bogo_get_qty`` at
      ``bogo_get_percent`` off (100 ⇒ free).

    The columns mirror :class:`services.promotions.PromoRule` so a row drops straight
    into the pure engine. Owner-scoped via ``user_id`` like every tenant entity.
    """

    __tablename__ = "promotions"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    kind = Column(String, nullable=False)  # line | category | bogo
    disc_type = Column(String, nullable=True)  # percentage | fixed (line/category)
    value = Column(Float, nullable=True)
    product_id = Column(Integer, nullable=True)  # line / bogo target
    category = Column(String, nullable=True)  # category target
    min_subtotal = Column(Float, nullable=True)  # auto-fire floor
    bogo_buy_qty = Column(Integer, nullable=True)
    bogo_get_qty = Column(Integer, nullable=True)
    bogo_get_percent = Column(Float, nullable=True)
    is_active = Column(Boolean, nullable=True, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
