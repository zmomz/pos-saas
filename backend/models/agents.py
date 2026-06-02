from core.database import Base
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Integer, String


class Agents(Base):
    __tablename__ = "agents"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False)
    company_name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    package_type = Column(Integer, nullable=False)
    used_slots = Column(Integer, nullable=True, default=0, server_default='0')
    logo_url = Column(String, nullable=True)
    primary_color = Column(String, nullable=True, default='#3B82F6', server_default='#3B82F6')
    secondary_color = Column(String, nullable=True, default='#1E40AF', server_default='#1E40AF')
    font_family = Column(String, nullable=True, default='Inter', server_default='Inter')
    button_radius = Column(String, nullable=True, default='8px', server_default='8px')
    is_active = Column(Boolean, nullable=True, default=True, server_default='true')
    default_language = Column(String, nullable=True, default='en', server_default='en')
    # Stripe Connect: the agent's connected-account id. When set, a client's
    # subscription charge is routed to the agent's gateway (CL-04 production path).
    stripe_account_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)