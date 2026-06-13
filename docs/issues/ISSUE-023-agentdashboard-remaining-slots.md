# ISSUE-023 — AgentDashboard reads real `remaining_slots`

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 2 · **Findings:** H9 · **Stories:** 25

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
AgentDashboard computes `remainingSlots` from `branding.client_slots/used_slots`, which `BrandingResponse` does not carry, while the real `remaining_slots`/`total` from `GET /agent/clients` is discarded — so the slot tile and footers always render 0/blank. Read `remaining_slots`/`total` from the clients response and drop the unused `client_slots`/`used_slots`/`package_type` interface fields.

## Acceptance criteria
- [ ] Slot tile and footers render the real remaining/total slot counts.
- [ ] Unused branding interface fields are removed.
- [ ] Guarded by a type/test.

## Blocked by
- None - can start immediately
