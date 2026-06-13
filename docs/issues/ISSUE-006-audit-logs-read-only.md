# ISSUE-006 — Make `audit_logs` router read-only

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 1 · **Findings:** H3 · **Stories:** 3

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
The audit trail currently exposes POST/PUT/DELETE + batch to any authenticated user, so actors can fabricate, edit, and delete their own audit history — defeating the purpose of a compliance log. Remove every write/delete endpoint; keep only owner/admin-scoped GET. The audit middleware remains the sole writer.

## Acceptance criteria
- [ ] All POST/PUT/DELETE/batch endpoints on `routers/audit_logs.py` are removed.
- [ ] GET endpoints remain (owner/admin scope is refined in ISSUE-012).
- [ ] A test asserts the removed verbs now return 404/405.
- [ ] Audit rows are still written by the middleware on normal requests.

## Blocked by
- None - can start immediately
