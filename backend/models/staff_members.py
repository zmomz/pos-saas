from core.database import Base
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Integer, String


class Staff_members(Base):
    __tablename__ = "staff_members"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    # The *owning* merchant's account id — the tenancy owner this staff row scopes
    # to. NOT the staff member's own login (see ``login_user_id``).
    user_id = Column(String, nullable=False)
    # SEC-11: the staff member's *own* login account id (FK to ``users.id``), set
    # when a login is provisioned for this row. Tenancy/permission resolution keys
    # on this immutable id rather than matching the mutable ``email`` column, so an
    # attacker cannot hijack a merchant's tenant by pre-registering the email.
    # Nullable: directory-only entries and rows whose email already belonged to a
    # pre-existing (unverified) account have no bound login.
    login_user_id = Column(String, nullable=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    role = Column(String, nullable=False)
    is_active = Column(Boolean, nullable=True)
    # Issue #216 — employee lifecycle state. ``is_active`` is the legacy
    # active/inactive toggle (kept for back-compat); ``status`` is the richer
    # workforce state the lifecycle endpoints drive:
    #   active     — working; full access.
    #   suspended  — access revoked, reversible (e.g. pending investigation).
    #   terminated — access revoked, permanent (off-boarded).
    # A staff member whose status is suspended/terminated is blocked at the auth
    # layer on their *own* login (see ``dependencies.auth._assert_account_active``),
    # so revocation is immediate and survives token replay.
    status = Column(String, nullable=False, default="active", server_default="active")
    # SEC: bcrypt hash of the staff member's numeric PIN, used for fast on-terminal
    # PIN login (``POST /auth/login/pin``). Null when no PIN is set. Never returned.
    pin_hash = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)