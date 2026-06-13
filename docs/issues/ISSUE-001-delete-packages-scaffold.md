# ISSUE-001 — Delete orphaned `packages` CRUD scaffold

**Status:** ready-for-agent · **Type:** AFK · **Sprint:** 1 · **Findings:** H1 · **Stories:** 1

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
Remove the orphaned duplicate package router/service that ships full CRUD + batch + **hard-delete** at `/api/v1/entities/packages` with no auth dependency. The real, master-gated, soft-delete path lives in `features.py` and must become the only package surface. Keep only the `normalize_feature_tier`/`parse_feature_tier` helpers from the service. Repoint the frontend `getPackages()` at the master-gated listing.

## Acceptance criteria
- [ ] `routers/packages.py` and `PackagesService` are deleted; `normalize_feature_tier`/`parse_feature_tier` are preserved (relocated if needed).
- [ ] No route serves create/update/delete of packages outside the master-gated `features.py` path.
- [ ] `getPackages()` resolves through the master-gated listing and the Packages UI still loads.
- [ ] `tests/test_orphan_routers.py`: `packages.py` moved to `REMOVED_BACKEND`, its `ALLOWLIST` entry dropped; suite green.

## Blocked by
- None - can start immediately
