# ISSUE-003 — Delete generic `permissions` CRUD scaffold

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 1 · **Findings:** H13 · **Stories:** 4

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
Remove the generic permissions CRUD router (`permissionss` typos) that scopes every read/write by `Permissions.user_id == current_user.id` — a contradictory self-ownership model where a user can only ever see/edit grants *about themselves*. There is no frontend caller. RBAC is enforced through `dependencies/permissions.py`; production permission management arrives in the Sprint-3 RBAC issues, not here.

## Acceptance criteria
- [ ] `routers/permissions.py`, `services/permissions.py`, and `data_models/permissions.json` are deleted.
- [ ] No `/api/v1/entities/permissions*` route is mounted; `require_permission` enforcement is unaffected.
- [ ] `tests/test_orphan_routers.py`: `permissions.py` moved to `REMOVED_BACKEND`, allowlist entry dropped; suite green.

## Blocked by
- None - can start immediately
