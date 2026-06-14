from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, String


class StoreSettings(Base):
    """Per-merchant store identity + operational defaults (ISSUE-079).

    One row per tenancy owner (``owner_user_id``) holding the merchant-level
    fields that are NOT already modelled on the ``clients`` row: the Commercial
    Registration (CR) number, the receipt footer line, the branch profile
    (address / city / phone) and the business hours (stored as a JSON string).

    The fiscally-authoritative seller name and VAT number stay on ``clients``
    (``business_name`` / ``vat_number``) — the store-settings screen writes those
    through so the existing receipt / invoice / ZATCA paths reflect a merchant's
    edits without changing those code paths.
    """

    __tablename__ = "store_settings"
    __table_args__ = {"extend_existing": True}

    owner_user_id = Column(String, primary_key=True, index=True)
    cr_number = Column(String, nullable=True)
    receipt_footer = Column(String, nullable=True)
    address = Column(String, nullable=True)
    city = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    # Business hours, persisted as a JSON string (a list of per-day
    # ``{day, open, close, closed}`` entries). Null until the merchant saves.
    business_hours = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
