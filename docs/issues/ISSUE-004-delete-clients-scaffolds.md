# ISSUE-004 — Delete `clients`/`client_features` scaffolds (incl. cross-tenant `/all`)

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 1 · **Findings:** H14, H15 · **Stories:** 5, 6

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
Remove the generic `clients`/`client_features` CRUD triads. Their service filters on `user_id == current_user.id` (the merchant's own login), so an agent/master can never read/mutate another tenant's clients/flags — structurally incapable. Their `GET /all` (admin-only, no agent filter) is also a cross-tenant exposure path. The working surface is `tenant.py::set_client_feature` + `require_feature`, driven by AgentDashboard. Deleting the files closes both H14 and the `/all` exposure (H15).

## Acceptance criteria
- [ ] `routers/clients.py`, `routers/client_features.py`, and their services are deleted (the unused `get_by_field`/`list_by_field`/`check_ownership` helpers go with them).
- [ ] No `/api/v1/entities/clients*` or `.../client_features*` route — including `/all` — is mounted.
- [ ] `tenant.py` per-client toggle + AgentDashboard still function.
- [ ] `tests/test_orphan_routers.py`: both files moved to `REMOVED_BACKEND`, allowlist entries dropped; suite green.

## Blocked by
- None - can start immediately
