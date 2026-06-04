from core.database import Base
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String


class Packages(Base):
    __tablename__ = "packages"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    name = Column(String, nullable=False)
    client_slots = Column(Integer, nullable=False)
    wholesale_price = Column(Float, nullable=False)
    suggested_retail_price = Column(Float, nullable=True)
    # MA-07 feature-entitlement tier: a JSON-encoded list of the feature keys this
    # package UNLOCKS (the enabled set). NULL ⇒ the package defines no tier and does
    # not restrict features (everything stays enabled-by-default). On provisioning
    # the tier seeds agent_features / client_features so a key outside the tier is
    # explicitly disabled. See services/packages.py::normalize_feature_tier.
    features = Column(String, nullable=True)
    is_active = Column(Boolean, nullable=True, default=True, server_default='true')
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)