from models.base import Base
from sqlalchemy import Boolean, Column, DateTime, String
from sqlalchemy.sql import func


class UserProfile(Base):
    """Per-user profile + notification preferences, persisted server-side.

    Keyed 1:1 to ``users.id`` so a user's display name and notification toggles
    follow them across devices (replacing the old localStorage-only state) and
    can drive server-side notification delivery (ISSUE-077).
    """

    __tablename__ = "user_profiles"

    user_id = Column(String(255), primary_key=True, index=True)
    display_name = Column(String(255), nullable=True)
    # Notification channel/category toggles. Defaults mirror the previous
    # frontend defaults so behaviour is unchanged for users who never saved.
    # ``email_alerts`` / ``whatsapp_alerts`` / ``push_alerts`` are the per-channel
    # master switches (M10 / parity #8); the new channels default off so an
    # upgrade never opts a user into a channel they never chose.
    email_alerts = Column(Boolean, nullable=False, default=True, server_default="true")
    whatsapp_alerts = Column(Boolean, nullable=False, default=False, server_default="false")
    push_alerts = Column(Boolean, nullable=False, default=False, server_default="false")
    low_stock_alerts = Column(Boolean, nullable=False, default=True, server_default="true")
    daily_summary = Column(Boolean, nullable=False, default=False, server_default="false")
    transaction_alerts = Column(Boolean, nullable=False, default=True, server_default="true")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
