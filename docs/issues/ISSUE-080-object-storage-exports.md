# ISSUE-080 — Working object storage / exports

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 4 · **Findings:** P2 settings / AG-07 · **Stories:** 55

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
Building on the storage decision (ISSUE-030), provide working object storage with real consumers: data/report exports a merchant can download (and the backing for product images). If ISSUE-030 chose deletion, this issue (re)introduces a minimal working storage path for exports.

## Acceptance criteria
- [ ] A merchant can generate and download at least one export (e.g. sales/catalog) backed by object storage.
- [ ] Storage operations succeed (no 500) and are owner-scoped.
- [ ] Covered by a test (request export → file retrievable).

## Blocked by
- ISSUE-030
