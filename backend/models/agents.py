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
    # MA-07: the package this agent was provisioned from. ``package_type`` already
    # carries the slot count; ``package_id`` retains the link so client provisioning
    # can derive the package's feature-entitlement tier (Packages.features). NULL
    # when the agent was created with an explicit slot count (no package, no tier).
    package_id = Column(Integer, nullable=True)
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
    # AG-05 deep white-label: the agent's own domain (e.g. "pos.acme.sa"). When set,
    # a request arriving on this host resolves the agent's branding so the merchant
    # login + funnel are served under the agent's brand, never the platform's.
    # Stored normalized (lowercase, no scheme/port/www); unique across agents.
    custom_domain = Column(String, nullable=True)
    # AG-06 branded transactional email: the agent's provisioning-email template.
    # Optional; when set it is rendered with {business_name}/{email}/{password}/
    # {login_url}/{brand} placeholders. When unset the branded default (carrying the
    # agent's company name + login URL) is used instead.
    email_template_subject = Column(String, nullable=True)
    email_template_body = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)