# ISSUE-027 — AuditLog page renders against real fields

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 2 · **Findings:** H5 · **Stories:** 27

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
AuditLog expects `user_email` and exact-match action verbs (`login`/`create`/…), but the writer stores verbose `POST /api/v1/entities/products` and the model has only `user_id` — so the user column is always `—`, badges always neutral, action filter matches nothing. Resolve `user_id`→email and emit normalized action verbs (backend), or rewrite the page to the real fields. With ISSUE-012 in place, the page also shows staff actions.

## Acceptance criteria
- [ ] User column shows the resolved email (or chosen real field).
- [ ] Action badges/colors and the action filter work against normalized verbs.
- [ ] The page shows staff actions for an owner (depends on owner-scoped reads).
- [ ] Covered by a test asserting the rendered shape matches what the backend returns.

## Blocked by
- ISSUE-012
