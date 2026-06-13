# ISSUE-100 — Remove duplicate CORS placeholder config

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 4 · **Findings:** U0.3 dead code · **Stories:** Further Notes

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
`middlewares/production.py::get_cors_config` is a duplicate with `yourdomain.com` placeholders; `core/cors.py` is the source of truth. Remove the duplicate.

## Acceptance criteria
- [ ] `get_cors_config` duplicate is removed; CORS comes only from `core/cors.py`.
- [ ] No placeholder origins remain in code.
- [ ] App boots; CORS behavior unchanged.

## Blocked by
- None - can start immediately
