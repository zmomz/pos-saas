# ISSUE-005 — Delete `entities/shifts` CRUD module

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 1 · **Findings:** H20 · **Stories:** 7

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
Remove the ~370-line orphaned shifts CRUD module at `/api/v1/entities/shifts` that lets clients PUT/DELETE arbitrary shift fields. The real shift lifecycle (open/close/movements/reconciliation) lives in `production.py` and is the only path the UI calls. Keep `models/shifts.py`.

## Acceptance criteria
- [ ] `routers/shifts.py` and `services/shifts.py` are deleted; `models/shifts.py` remains.
- [ ] No `/api/v1/entities/shifts*` route is mounted; the `production.py` shift lifecycle is unaffected.
- [ ] `tests/test_orphan_routers.py`: `shifts.py` moved to `REMOVED_BACKEND`, allowlist entry dropped; suite green.

## Blocked by
- None - can start immediately
