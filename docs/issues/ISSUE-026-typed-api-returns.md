# ISSUE-026 — Typed API return signatures on drift-prone endpoints

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 2 · **Findings:** systemic (theme #5) · **Stories:** 28

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
Response-shape drift silently zeroed multiple UIs. Give the drift-prone `api.ts` functions explicit typed return signatures (products list, expenses, agent clients/slots, master metrics, discounts) so a future shape mismatch is a TypeScript compile error rather than a silent empty render. This is the durable guard behind ISSUE-021…025.

## Acceptance criteria
- [ ] The endpoints fixed in ISSUE-021…025 have explicit typed return signatures matching the backend response models.
- [ ] Reading a non-existent field on those responses fails `tsc`.
- [ ] Frontend type-check passes in CI.

## Blocked by
- ISSUE-021, ISSUE-022, ISSUE-023, ISSUE-024, ISSUE-025
