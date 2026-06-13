# ISSUE-007 — Make `api_usage` router read-only

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 1 · **Findings:** H3 · **Stories:** 3

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
The `api_usage` router exposes the same user-writable/deletable surface as the audit log. Metering rows are written by the metering middleware + `production.py` stats; no user should write or delete them. Remove every write/delete endpoint; keep only owner/admin-scoped GET.

## Acceptance criteria
- [ ] All POST/PUT/DELETE/batch endpoints on `routers/api_usage.py` are removed.
- [ ] GET endpoints remain (owner/admin scope refined in ISSUE-012).
- [ ] A test asserts the removed verbs now return 404/405.
- [ ] Metering is still recorded by the middleware on normal requests.

## Blocked by
- None - can start immediately
