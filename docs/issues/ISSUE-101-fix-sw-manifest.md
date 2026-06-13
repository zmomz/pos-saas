# ISSUE-101 — Fix `sw.js` manifest reference

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 4 · **Findings:** U0.3 dead binding · **Stories:** Further Notes

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
`frontend/public/sw.js` lists `/manifest.webmanifest` in its SHELL precache, but the file does not exist — and a failed `addAll` voids the entire precache. Remove the bad entry (or add the manifest) so the service-worker shell caches successfully.

## Acceptance criteria
- [ ] `sw.js` SHELL precache succeeds (no missing-resource failure).
- [ ] Either `/manifest.webmanifest` exists and is valid, or the reference is removed.
- [ ] Verified the service worker installs/activates without an `addAll` rejection.

## Blocked by
- None - can start immediately
