"""Platform-settings key/value store (M10 Admin, #225).

Operator-console state that is **platform-global** rather than tenant-owned —
the first user being *maintenance mode*. Unlike ``store_settings`` (owned by a
client merchant), these rows belong to the platform itself and are only ever
read/written by the platform master, so they carry no ``user_id`` tenancy
column: a single row per ``key`` is the whole platform's value.

A generic key/value shape (rather than a bespoke column per flag) lets the admin
console grow — feature-flag console, job-monitor toggles, etc. — without a new
migration per setting. The ``value`` is JSON-encoded text so a setting can hold a
scalar or a small object (e.g. maintenance mode's ``{enabled, message}``).
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, String, Text

from core.database import Base


class PlatformSetting(Base):
    __tablename__ = "platform_settings"
    __table_args__ = {"extend_existing": True}

    # The setting name is the primary key — one row per platform-global setting.
    key = Column(String, primary_key=True, index=True, nullable=False)
    # JSON-encoded payload (scalar or small object). Nullable ⇒ "unset".
    value = Column(Text, nullable=True)
    # Who last changed it (master user id) and when — audit breadcrumbs surfaced
    # by the console.
    updated_by = Column(String, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
