# ISSUE-078 — Persisted per-user profile

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 4 · **Findings:** P2 settings / U6.1 · **Stories:** 55

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
UserProfile is localStorage-only. Persist per-user profile + notification preferences server-side so they survive devices and drive notification delivery.

## Acceptance criteria
- [ ] Profile + notification prefs persist server-side, scoped to the user.
- [ ] Loading the profile on another device returns the saved values.
- [ ] Covered by a test (save → reload returns values).

## Blocked by
- None - can start immediately
