# ISSUE-030 — Storage router: make it work or delete it

**Status:** ready-for-agent · **Type:** HITL · **Sprint:** 2 · **Findings:** H27 · **Stories:** 32

## Parent
[PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md)

## What to build
`StorageService()` reads `settings.oss_service_url`/`oss_api_key`, neither of which exists on `Settings` (`extra="ignore"`), so init raises `AttributeError` → all 8 storage endpoints return 500. HITL decision: either (a) add the config keys (degrading to a clear `ValueError`, not a 500) plus a real caller, or (b) delete `routers/storage.py` + `services/storage.py` + schemas (and clear the allowlist entry). It must not remain a 500 façade.

## Acceptance criteria
- [ ] Decision recorded (work vs delete).
- [ ] If kept: config keys added, init degrades gracefully, a real caller exists, endpoints return non-500; covered by a test.
- [ ] If deleted: router/service/schemas removed, `tests/test_orphan_routers.py` updated (`REMOVED_BACKEND`, allowlist entry dropped).

## Blocked by
- ISSUE-020
