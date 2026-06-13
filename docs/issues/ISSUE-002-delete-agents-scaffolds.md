# ISSUE-002 — Delete `agents`/`agent_features` CRUD scaffolds

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 1 · **Findings:** H2 · **Stories:** 2

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
Remove the generic CRUD scaffolds at `/api/v1/entities/agents|agent_features` (tell-tale `agentss` plurals) that let any authenticated user CRUD agent/branding rows by `user_id`. The real branding/provisioning surface is `tenant.py`/`features.py`. Keep the SQLAlchemy models — they are used by those modules.

## Acceptance criteria
- [ ] `routers/agents.py`, `services/agents.py`, `routers/agent_features.py`, `services/agent_features.py` are deleted.
- [ ] `models/agents.py`/`agent_features` models remain and `tenant.py`/`features.py` still import them cleanly.
- [ ] No `/api/v1/entities/agents*` route is mounted.
- [ ] `tests/test_orphan_routers.py`: both files moved to `REMOVED_BACKEND`, allowlist entries dropped; suite green.

## Blocked by
- None - can start immediately
