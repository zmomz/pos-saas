from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String


class Audit_logs(Base):
    __tablename__ = "audit_logs"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, nullable=False)  # the *actor* — the JWT ``sub`` that performed the action
    # The owning merchant this row belongs to (resolved via the tenant scope). A
    # staff member's actions are tagged with their owner so the merchant's audit
    # query surfaces all staff activity, not just the owner's own (finding H4).
    owner_user_id = Column(String, nullable=True, index=True)
    action = Column(String, nullable=False)
    details = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)
    # Audit-completeness (Phase 3): the affected entity and the submitted change
    # set. ``entity_type``/``entity_id`` are parsed from the request path;
    # ``changes`` is the JSON request body ("after" state) with sensitive keys
    # redacted. Failed-auth attempts are recorded with action ``AUTH_FAILURE``.
    entity_type = Column(String, nullable=True)
    entity_id = Column(String, nullable=True)
    changes = Column(String, nullable=True)
    # Tamper-evidence (ISSUE-019): each row is linked to the prior row by a
    # SHA-256 chain. ``prev_hash`` is the preceding row's ``row_hash`` (a genesis
    # constant for the first row); ``row_hash`` = sha256(prev_hash + canonical
    # content). ``services.audit.verify_audit_chain`` re-walks the chain so a
    # mutated or removed row is detectable. Nullable only to tolerate pre-ISSUE-019
    # rows on an already-migrated database.
    prev_hash = Column(String, nullable=True)
    row_hash = Column(String, nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)